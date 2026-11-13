#!/usr/bin/env python3
"""Guarded backup of a running NoSketch Docker deployment (Python 3.9+)."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CHUNK = 4 * 1024 * 1024


def fail(message):
    raise RuntimeError(message)


def run(args, *, stdout=subprocess.PIPE, log=None):
    with (open(log, "wb") if log else open(os.devnull, "wb")) as err:
        proc = subprocess.run(args, stdout=stdout, stderr=err, check=False)
    if proc.returncode:
        fail(f"Command {args[0]!r} failed (exit {proc.returncode}); see private log if provided")
    return proc.stdout


def docker_json(prefix, args):
    return json.loads(run(prefix + args).decode("utf-8"))


def inspect(prefix, name):
    objs = docker_json(prefix, ["inspect", "--type", "container", name])
    if len(objs) != 1:
        fail("Expected exactly one Docker container")
    obj = objs[0]
    if obj.get("State", {}).get("Running") is not True:
        fail("Container is not running; do not attempt to start or replace it here")
    mount = [m for m in obj.get("Mounts", []) if m.get("Destination") == "/corpora"]
    if len(mount) != 1 or mount[0].get("Type") != "bind":
        fail("Expected exactly one direct bind mount at /corpora; inspect manually")
    if any(m.get("Destination", "").startswith("/corpora/") for m in obj.get("Mounts", [])):
        fail("Nested /corpora mounts require a manual backup plan")
    source = Path(mount[0]["Source"]).resolve(strict=True)
    if not source.is_dir():
        fail("Corpus source is not a directory")
    return obj, source


def validate_destination(destination, source, *, existing=False):
    if not destination.is_absolute() or destination == Path("/"):
        fail("Destination must be an absolute, non-root path")
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            fail("Symlink in destination ancestry is not allowed")
    resolved = destination.resolve(strict=False)
    protected = (source, source.parent, ROOT)
    if any(resolved == p or resolved.is_relative_to(p) for p in protected):
        fail("Destination lies inside the corpus/deployment source or public repository")
    if any(p.is_relative_to(resolved) for p in (source, ROOT)):
        fail("Destination must not contain corpus source or repository")
    if existing:
        if not destination.is_dir() or destination.stat().st_mode & 0o077:
            fail("Existing destination must be a private directory (mode 0700)")
    elif destination.exists():
        fail("Destination already exists; use --continue only for a matching prior backup")
    if not destination.parent.is_dir():
        fail("Destination parent directory does not exist")
    return resolved


def preflight(prefix, name, destination):
    obj, source = inspect(prefix, name)
    validate_destination(destination, source, existing=False)
    if os.geteuid() != 0:
        fail("Run preflight and backup with sudo to inspect protected files")
    for utility in ("rsync", "tar"):
        if not shutil.which(utility):
            fail(f"Required executable not found: {utility}")
    image = docker_json(prefix, ["image", "inspect", obj["Image"]])[0]
    # No environment values, raw inspect or credentials are printed.
    source_bytes = int(run(["du", "-sB1", str(source)]).decode().split()[0])
    free = shutil.disk_usage(destination.parent).free
    report = {
        "container": name, "running": True,
        "auto_remove": obj.get("HostConfig", {}).get("AutoRemove"),
        "image_id": obj["Image"], "image_bytes": image.get("Size"),
        "corpus_source": str(source), "corpus_bytes_estimate": source_bytes,
        "destination": str(destination), "destination_free_bytes": free,
        "destination_same_device_as_corpora": destination.parent.stat().st_dev == source.stat().st_dev,
        "destination_capacity_warning": free < (source_bytes * 1.2 + int(image.get("Size") or 0) * 2),
        "note": "No writes to Docker or corpus sources. Live copies are not atomic snapshots."
    }
    return report


def write_json(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")
    path.chmod(0o600)


def archive_stream(argv, destination):
    if destination.exists():
        fail(f"Refusing to overwrite existing archive: {destination.name}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        fail(f"Partial archive exists: {partial}; use a new backup directory")
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with partial.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                while True:
                    block = proc.stdout.read(CHUNK)
                    if not block:
                        break
                    compressed.write(block)
        proc.stdout.close()
        if proc.wait() != 0:
            fail(f"Archive command {argv[0]!r} failed; backup stage incomplete")
        partial.rename(destination)
    except BaseException:
        proc.stdout.close()
        proc.kill() if proc.poll() is None else None
        proc.wait()
        raise


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def save_manifest(destination, data):
    path = destination / "manifest.json"
    tmp = destination / ".manifest.json.partial"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def load_manifest(destination):
    with (destination / "manifest.json").open(encoding="utf-8") as f:
        return json.load(f)


def log_rsync(args, path):
    with path.open("wb") as f:
        result = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, check=False)
    path.chmod(0o600)
    if result.returncode:
        fail(f"rsync failed (exit {result.returncode}); inspect private {path}")


def backup(prefix, name, destination, phase, resume, allow_same_filesystem=False):
    if os.geteuid() != 0:
        fail("Backups must be run with sudo (root privileges)")
    obj, source = inspect(prefix, name)
    validate_destination(destination, source, existing=resume)
    if not shutil.which("rsync") or not shutil.which("tar"):
        fail("rsync and tar are required")
    if phase in ("corpora", "all") and (destination if resume else destination.parent).stat().st_dev == source.stat().st_dev and not allow_same_filesystem:
        fail("Corpus backup destination is on the SAME filesystem as the source; "
             "use independent storage or explicitly accept risk with --allow-same-filesystem")
    image_size = int(docker_json(prefix, ["image", "inspect", obj["Image"]])[0].get("Size") or 0)
    free_bytes = shutil.disk_usage(destination if resume else destination.parent).free
    # Conservatively allow room for compressed image + rootfs export and transfer.
    margin = 512 * 1024 * 1024
    state_estimate = 0 if (resume and phase == "corpora") else image_size * 2
    if free_bytes < state_estimate + margin:
        fail("Insufficient free space for minimum state backup estimate")
    if phase in ("corpora", "all"):
        source_bytes = int(run(["du", "-sB1", str(source)]).decode().split()[0])
        if free_bytes < source_bytes + state_estimate + margin:
            fail("Insufficient free space for estimated full corpus + state backup")
    if resume:
        manifest = load_manifest(destination)
        if (manifest["container"] != name or manifest["image_id"] != obj["Image"]
                or manifest["corpus_source"] != str(source)):
            fail("Live container/image/corpus mapping differs from existing backup")
    else:
        destination.mkdir(mode=0o700)
        manifest = {"schema": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "container": name, "image_id": obj["Image"],
                    "corpus_source": str(source), "state_complete": False,
                    "corpora_complete": False, "archives": {},
                    "consistency": "live copy; no filesystem snapshot or application quiescence"}
        save_manifest(destination, manifest)
    if phase in ("state", "all") and not manifest["state_complete"]:
        private = destination / "private"
        artifacts = destination / "artifacts"
        private.mkdir(mode=0o700, exist_ok=True)
        artifacts.mkdir(mode=0o700, exist_ok=True)
        # Raw inspect contains secrets; never commit or share these files.
        write_json(private / "container-inspect.json", obj)
        write_json(private / "image-inspect.json",
                   docker_json(prefix, ["image", "inspect", obj["Image"]])[0])
        with (private / "docker-diff.txt").open("xb") as f:
            f.write(run(prefix + ["diff", name]))
        print("Capturing Bonito application state...", flush=True)
        archive_stream(prefix + ["cp", f"{name}:/var/lib/bonito", "-"],
                       artifacts / "bonito.tar.gz")
        print("Saving original Docker image...", flush=True)
        archive_stream(prefix + ["image", "save", obj["Image"]],
                       artifacts / "original-image.tar.gz")
        print("Exporting current container root filesystem (excludes mounts)...", flush=True)
        archive_stream(prefix + ["export", name],
                       artifacts / "container-rootfs-export.tar.gz")
        checkout = source.parent
        if checkout.is_dir():
            (private / "deployment").mkdir(mode=0o700)
            log_rsync(["rsync", "-aHAX", "--numeric-ids", "--one-file-system",
                       "--exclude=/corpora/", str(checkout) + "/",
                       str(private / "deployment") + "/"], private / "deployment-rsync.log")
        if Path("/etc/nginx").is_dir():
            archive_stream(["tar", "-C", "/etc", "-cf", "-", "nginx"],
                           artifacts / "host-nginx.tar.gz")
        for item in artifacts.glob("*.tar.gz"):
            manifest["archives"][item.name] = {"sha256": sha256(item), "bytes": item.stat().st_size}
        manifest["state_complete"] = True
        save_manifest(destination, manifest)
        print("Container state capture complete; protected private/ contains secrets.")
    if phase == "corpora" and not manifest["state_complete"]:
        fail("Capture state first; corpora-only phase requires completed state backup")
    if phase in ("corpora", "all") and not manifest["corpora_complete"]:
        if not manifest["state_complete"]:
            fail("State stage must complete before corpus copy")
        target = destination / "corpora"
        target.mkdir(mode=0o700, exist_ok=True)
        print("Copying corpora with rsync; source remains untouched...", flush=True)
        log_rsync(["rsync", "-aHAX", "--numeric-ids", "--one-file-system",
                   "--partial", "--stats", str(source) + "/", str(target) + "/"],
                  destination / "corpora-rsync.log")
        manifest["corpora_complete"] = True
        save_manifest(destination, manifest)
        print("Corpus transfer complete. Run verify with --compare-live.")
    if (phase == "state" and manifest["state_complete"] or
            phase == "corpora" and manifest["corpora_complete"]):
        print("Requested phase marked complete.")
    print(f"Backup directory: {destination}")


def verify(destination, compare_live):
    manifest = load_manifest(destination)
    if not manifest["state_complete"]:
        fail("State backup is incomplete")
    mandatory = {"bonito.tar.gz", "original-image.tar.gz", "container-rootfs-export.tar.gz"}
    if not mandatory.issubset(manifest["archives"]):
        fail("Mandatory container-state archives missing from manifest")
    for name, info in manifest["archives"].items():
        path = destination / "artifacts" / name
        if not path.is_file() or path.stat().st_size != info["bytes"] or sha256(path) != info["sha256"]:
            fail(f"Archive verification failed: {name}")
        print(f"OK SHA256: {name}")
    for name in ("container-inspect.json", "image-inspect.json", "docker-diff.txt"):
        if not (destination / "private" / name).is_file():
            fail(f"Missing sensitive metadata file: {name}")
    if manifest["corpora_complete"] and not (destination / "corpora").is_dir():
        fail("Missing backed-up corpus directory")
    if compare_live:
        if not manifest["corpora_complete"]:
            fail("No completed corpus copy to compare")
        report = destination / "live-compare-rsync.log"
        # --delete is strictly paired with --dry-run here. No files are deleted.
        log_rsync(["rsync", "-aHAX", "--numeric-ids", "--one-file-system", "--checksum",
                   "--dry-run", "--delete", "--itemize-changes",
                   manifest["corpus_source"] + "/", str(destination / "corpora") + "/"], report)
        if report.stat().st_size:
            fail("Live corpus differs from backup; see private live-compare-rsync.log. "
                 "Live writes after capture can cause this result")
        print("OK: checksum-based live corpus comparison (at time of check)")
    print("Archive verification passed. Isolated restoration test is still mandatory.")
    if not manifest["corpora_complete"]:
        print("WARNING: corpus backup is NOT complete")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("preflight", "backup"):
        parser = sub.add_parser(cmd)
        parser.add_argument("--container", default="noske")
        parser.add_argument("--docker-command", default="docker")
        parser.add_argument("--destination", required=True, type=Path)
        if cmd == "backup":
            parser.add_argument("--execute", action="store_true")
            parser.add_argument("--phase", choices=("state", "corpora", "all"), default="state")
            parser.add_argument("--continue", dest="resume", action="store_true")
            parser.add_argument("--allow-same-filesystem", action="store_true")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--destination", required=True, type=Path)
    verify_parser.add_argument("--compare-live", action="store_true")
    args = p.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "verify":
            verify(args.destination, args.compare_live)
        elif args.command == "preflight":
            prefix = shlex.split(args.docker_command)
            print(json.dumps(preflight(prefix, args.container, args.destination),
                             indent=2, ensure_ascii=False))
        else:
            if not args.execute:
                fail("Refusing backup without explicit --execute; run preflight first")
            prefix = shlex.split(args.docker_command)
            backup(prefix, args.container, args.destination, args.phase, args.resume, args.allow_same_filesystem)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
