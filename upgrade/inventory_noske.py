#!/usr/bin/env python3
"""Read-only inventory of a running NoSketch Engine Docker deployment.

Uses Docker inspect, image inspect and read-only exec commands, plus local
filesystem metadata and selected nginx proxy directives. No server settings
or Docker objects are changed. Reports are written outside the Git checkout.
Python 3.9+, no third-party libraries.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys

ENV_ALLOWLIST = {"SERVER_NAME", "SERVER_ALIAS", "LANG", "LC_ALL",
                 "LC_CTYPE", "TZ", "MANATEE_REGISTRY", "CITATION_LINK"}
COMPOSE_LABELS = {"com.docker.compose.project", "com.docker.compose.service",
                  "com.docker.compose.project.working_dir",
                  "com.docker.compose.project.config_files"}


def command(argv, timeout=45):
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Command unavailable or timed out: " + argv[0]) from exc
    if result.returncode:
        # Do not put arbitrary stderr (potentially sensitive) in the report.
        raise RuntimeError(f"Command {argv[0]} exited with code {result.returncode}")
    return result.stdout


def optional_command(argv):
    try:
        return command(argv), None
    except RuntimeError as exc:
        return None, str(exc)


def docker_json(prefix, args):
    return json.loads(command(prefix + args))


def safe_value(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9:/._+-]{1,200}", value):
        return value
    return "[set; value redacted]"


def environment(entries):
    keys, allowed = [], {}
    for item in entries or []:
        key, separator, value = item.partition("=")
        if separator:
            keys.append(key)
            if key in ENV_ALLOWLIST:
                allowed[key] = safe_value(value)
    return sorted(set(keys)), allowed


def mounts_of(items):
    return [{
        "type": item.get("Type"), "source": item.get("Source"),
        "destination": item.get("Destination"), "name": item.get("Name"),
        "read_write": item.get("RW"),
        "propagation": item.get("Propagation"),
    } for item in items or []]


def covering_mount(path, mounts):
    matches = [m for m in mounts if m.get("destination") and
               (m["destination"] == "/" or
                path == m["destination"].rstrip("/") or
                path.startswith(m["destination"].rstrip("/") + "/"))]
    return max(matches, key=lambda m: len(m["destination"]), default=None)


def directory_info(path):
    data = {"path": str(path), "exists": False}
    try:
        data["exists"] = path.exists()
        if path.exists():
            data["realpath"] = str(path.resolve())
            data["is_directory"] = path.is_dir()
            if path.is_dir():
                with os.scandir(path) as iterator:
                    entries = list(iterator)
                data["immediate_files"] = sum(e.is_file(follow_symlinks=False) for e in entries)
                data["immediate_directories"] = sum(e.is_dir(follow_symlinks=False) for e in entries)
                data["first_30_names"] = sorted(e.name for e in entries)[:30]
                usage = shutil.disk_usage(path)
                data["filesystem_bytes"] = {
                    "total": usage.total, "used": usage.used, "free": usage.free}
    except OSError:
        data["error"] = "Cannot inspect path with current user permissions"
    return data


def corpora_info(mount):
    if not mount:
        return {"status": "No mount found for /corpora"}
    if mount["type"] != "bind":
        return {"status": "Not a bind mount; examine volume mapping", "mount": mount}
    root = Path(mount["source"])
    data = {"status": "bind mount", "root": directory_info(root),
            "registry": directory_info(root / "registry")}
    try:
        with os.scandir(root) as iterator:
            names = sorted(e.name for e in iterator
                           if e.is_dir(follow_symlinks=False) and e.name != "registry")
        data["corpus_directory_count"] = len(names)
        data["sample_corpus_layouts"] = [
            {"name": name, "vertical_exists": (root / name / "vertical").is_dir(),
             "indexed_exists": (root / name / "indexed").is_dir()}
            for name in names[:30]]
    except OSError:
        data["error"] = "Cannot list corpus root as current user"
    return data


def read_only_exec(prefix, name):
    data = {}
    release, err = optional_command(prefix + ["exec", name, "cat", "/etc/os-release"])
    if err:
        data["os_release_error"] = err
    else:
        data["os_release"] = {
            k: v.strip('"') for row in release.splitlines() if "=" in row
            for k, v in [row.split("=", 1)] if k in ("PRETTY_NAME", "ID", "VERSION_ID")}
    packages, err = optional_command(prefix + ["exec", name, "dpkg-query", "-W"])
    if err:
        data["packages_error"] = err
    else:
        data["noske_packages"] = [
            line for line in packages.splitlines()
            if re.search(r"manatee|bonito|crystal|gdex", line, re.I)]
    locales, err = optional_command(prefix + ["exec", name, "locale", "-a"])
    if err:
        data["locales_error"] = err
    else:
        data["locales"] = locales.splitlines()[:100]
    for target in ("/var/lib/bonito", "/var/www/bonito"):
        listing, err = optional_command(prefix + ["exec", name, "ls", "-A", target])
        data[target] = {"accessible": err is None,
                        "immediate_entry_count": len(listing.splitlines())
                        if listing is not None else None}
    return data


def nginx_info():
    data = {"config_directories": [], "loopback_proxy_references": []}
    status, _ = optional_command(["systemctl", "is-active", "nginx"])
    data["systemd_status"] = (status or "unknown").strip()
    pattern = re.compile(
        r"\bproxy_pass\s+https?://(127\.0\.0\.1|localhost|\[::1\]):(\d+)\b",
        re.I)
    for folder_name in ("/etc/nginx/sites-enabled", "/etc/nginx/conf.d"):
        folder = Path(folder_name)
        if not folder.is_dir():
            continue
        data["config_directories"].append(folder_name)
        try:
            paths = sorted(p for p in folder.iterdir() if p.is_file())
        except OSError:
            continue
        for path in paths:
            try:
                if path.stat().st_size > 512 * 1024:
                    continue
                config = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in pattern.finditer(config):
                data["loopback_proxy_references"].append({
                    "config_file": str(path), "host": match.group(1),
                    "port": int(match.group(2))})
    return data


def as_markdown(data):
    c = data["container"]
    md = ["# NoSketch Engine — read-only Docker inventory", "",
          f"Collected UTC: {data['collected_utc']}",
          f"Host: {data['host']}",
          f"Container: {c['name']}",
          f"Image reference: {c['image_reference']}",
          f"Image ID: {c['image_id']}",
          f"Created: {c['created']}",
          f"Running status: {c['status']}",
          f"AutoRemove: {c['auto_remove']}",
          f"Restart policy: {json.dumps(c['restart_policy'])}",
          f"Published ports: {json.dumps(c['ports'], ensure_ascii=False)}",
          "", "## Mounts", "",
          "| Type | Host source / volume | Container destination | RW |",
          "| --- | --- | --- | --- |"]
    for m in c["mounts"]:
        fields = [m["type"], m["source"], m["destination"], m["read_write"]]
        md.append("| " + " | ".join(str(v).replace("|", "\\|") for v in fields) + " |")
    for label, value in (
        ("HostConfig.Binds (original mount specifications)", c["host_binds"]),
        ("HostConfig.Mounts", c["host_mounts"]),
        ("Network, runtime, and safe environment", {
            "network_mode": c["network_mode"], "user": c["user"],
            "working_dir": c["working_dir"], "privileged": c["privileged"],
            "readonly_rootfs": c["readonly_rootfs"],
            "environment_keys_only": c["environment_keys"],
            "allowlisted_environment": c["allowlisted_environment"],
            "compose_labels": c["compose_labels"]}),
        ("Image metadata", data["image"]),
        ("Corpus root and immediate layouts", data["corpora"]),
        ("Container OS, packages, locales, state directories", data["inside_container"]),
        ("nginx (localhost upstreams only)", data["nginx"]),
    ):
        md.extend(["", "## " + label, "", "~~~json",
                   json.dumps(value, indent=2, ensure_ascii=False), "~~~"])
    md.extend(["", "## Warnings", ""])
    md.extend("- " + line for line in data["warnings"])
    md.extend(["", "## Report handling", "",
               "No full Docker inspect, certificate, credential, complete nginx",
               "configuration or non-allowlisted environment value is exported.",
               "Host paths and corpus names can still be sensitive. Review before",
               "sharing. Do NOT commit generated reports into the public repository.",
               "This inventory does not establish binary index compatibility.", ""])
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="noske")
    parser.add_argument("--docker-command", default="sudo docker",
                        help='Default: "sudo docker"; specify "docker" if permitted')
    parser.add_argument("--output-dir", type=Path,
                        help="New, nonexistent output directory; defaults under home")
    parser.add_argument("--skip-container-exec", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    prefix = shlex.split(args.docker_command)
    if not prefix:
        parser.error("empty Docker command")
    print(f"Collecting read-only Docker inventory for {args.container}...")
    try:
        objs = docker_json(prefix, ["inspect", "--type", "container", args.container])
        if len(objs) != 1:
            raise RuntimeError("Expected exactly one container")
        obj = objs[0]
        image_id = obj["Image"]
        image = docker_json(prefix, ["image", "inspect", image_id])[0]
    except (RuntimeError, ValueError, KeyError, IndexError) as exc:
        print(f"ERROR: Unable to inspect Docker container/image: {exc}",
              file=sys.stderr)
        return 2
    config = obj.get("Config") or {}
    hostconfig = obj.get("HostConfig") or {}
    network = obj.get("NetworkSettings") or {}
    keys, allowed = environment(config.get("Env"))
    mounts = mounts_of(obj.get("Mounts"))
    labels = config.get("Labels") or {}
    data = {
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "container": {
            "name": obj.get("Name", args.container).lstrip("/"),
            "id": obj.get("Id"),
            "image_id": image_id,
            "image_reference": config.get("Image"),
            "created": obj.get("Created"),
            "status": (obj.get("State") or {}).get("Status"),
            "mounts": mounts,
            "host_binds": hostconfig.get("Binds") or [],
            "host_mounts": hostconfig.get("Mounts") or [],
            "ports": network.get("Ports") or {},
            "auto_remove": hostconfig.get("AutoRemove"),
            "restart_policy": hostconfig.get("RestartPolicy") or {},
            "network_mode": hostconfig.get("NetworkMode"),
            "user": config.get("User"),
            "working_dir": config.get("WorkingDir"),
            "privileged": hostconfig.get("Privileged"),
            "readonly_rootfs": hostconfig.get("ReadonlyRootfs"),
            "environment_keys": keys,
            "allowlisted_environment": allowed,
            "compose_labels": {k: safe_value(labels[k]) for k in COMPOSE_LABELS
                               if k in labels},
        },
        "image": {
            "id": image.get("Id"), "created": image.get("Created"),
            "repo_tags": image.get("RepoTags") or [],
            "repo_digests": image.get("RepoDigests") or [],
            "os": image.get("Os"), "architecture": image.get("Architecture"),
        },
        "corpora": corpora_info(covering_mount("/corpora", mounts)),
        "inside_container": ({"skipped": True} if args.skip_container_exec
                             else read_only_exec(prefix, args.container)),
        "nginx": nginx_info(),
        "warnings": [],
    }
    warnings = data["warnings"]
    if not covering_mount("/corpora", mounts):
        warnings.append("CRITICAL: no Docker mount covers /corpora.")
    if hostconfig.get("AutoRemove"):
        warnings.append("AutoRemove=true: stopping may delete the old writable layer.")
    if not covering_mount("/var/lib/bonito", mounts):
        warnings.append("/var/lib/bonito is not mounted: Bonito state may not survive removal.")
    if any(bound and any(item.get("HostIp") in ("0.0.0.0", "::", "")
                         for item in bound)
           for bound in (network.get("Ports") or {}).values()):
        warnings.append("A published port is bound beyond localhost; review firewall exposure.")
    warnings.append("Do not invoke docker stop/rm, make clean, or make compile during inventory.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or (Path.home() / ("noske-inventory-" + stamp))
    try:
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
        json_path = output / "inventory.json"
        md_path = output / "inventory.md"
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        md_path.write_text(as_markdown(data), encoding="utf-8")
        json_path.chmod(0o600)
        md_path.chmod(0o600)
    except OSError as exc:
        print(f"ERROR: cannot write local inventory: {exc}", file=sys.stderr)
        return 3
    print(f"Report: {md_path}")
    print(f"Structured data: {json_path}")
    print("No production Docker, nginx, or corpus changes were made.")
    print("Review/redact reports before sharing; do not commit them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
