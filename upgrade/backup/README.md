# NoSketch Engine production backup (guarded)

This procedure is for the running container on `nosketchtest`, **before any stop, restart, container replacement or corpus recompilation**. It only reads Docker and source data, and writes to a new, private destination. It is **not** an application-consistent snapshot: active application/corpus writes can make a live copy inconsistent. Never interpret a successful `rsync` exit as proof of recoverability.

## Requirements

- Linux host with Docker, Python **3.9+**, GNU `du`, GNU `tar` and `rsync`, with root privileges (`sudo`).
- Know the current container name (`noske` by default). The script inspects its **actual** `/corpora` bind mount; never trusts an assumed checkout path or the mutable `latest` image tag.
- An approved backup location, preferably independent storage with an encrypted, off-host copy. It must be outside the corpus source and Git checkout; the destination parent must exist. **Choose a new destination name** and do not create that final directory yourself. Its contents will include private credentials and internal paths.
- Sufficient free space for the **full corpus data**, original image, Bonito state, and exported container filesystem. A full image and rootfs export may each be large. Run during low I/O activity and **ensure no corpus compilation is underway**.
- Verify whether source symlinks reference files **outside** the corpus mount and whether additional host mounts exist under that source; `rsync` preserves symbolic links but does not follow them, and uses `--one-file-system`. These cases require explicit additional backup work.

## Commands

```bash
cd /home/valdiss/github/HowTo_NoSketch
git pull --ff-only
python3 -m unittest discover -s upgrade/tests -v

# Choose an existing, access-controlled destination PARENT (example only).
# This path must be changed to an actual authorized backup location.
BACKUP=/mnt/APPROVED-BACKUP/noske-$(date -u +%Y%m%dT%H%M%SZ)

# 1. No writes; prints estimates and explicit capacity warnings.
sudo python3 upgrade/backup/preflight_backup.py --destination "$BACKUP"

# 2. Capture irreplaceable container state FIRST.
sudo bash upgrade/backup/backup_noske.sh --destination "$BACKUP" --phase state --execute

# 3. Verify archive hashes even before the potentially long corpus transfer.
sudo python3 upgrade/backup/verify_backup.py --destination "$BACKUP"

# 4. Transfer registry, verticals, compiled indexes, and other corpus files.
sudo bash upgrade/backup/backup_noske.sh --destination "$BACKUP" --phase corpora --continue --execute

# 5. Check archive hashes and compare all corpus bytes/metadata with live source.
# --compare-live uses rsync --dry-run --checksum (and --delete ONLY with --dry-run).
sudo python3 upgrade/backup/verify_backup.py --destination "$BACKUP" --compare-live
```

For Docker access without running as root, root is **still required for filesystem ownership, extended attributes, and protected configuration**. The `--docker-command` option defaults to `docker` because all documented commands run via `sudo`. If the container name differs, pass `--container YOUR_CONTAINER` for preflight and backup.

The two execution phases deliberately allow backing up vulnerable container state first. To rerun **a failed corpus transfer**, use the same `--phase corpora --continue --execute` command. `rsync --partial` allows existing destination files to be reused. An interrupted **state** capture requires a *new* backup directory; incomplete archives are not silently reused or overwritten. A stage already marked complete is skipped on a matching `--continue`, which checks the image ID and corpus mount source.

`--allow-same-filesystem` is available as an explicit, high-risk override if an approved independent destination is unavailable; do not use it without verifying space and backup isolation. By default a full corpus copy to the same source filesystem is refused.

`--phase all` is also supported for a fresh backup, but is not preferred for the first production run because the large corpus transfer may take substantial time.

## Transfer progress

The corpus-copy phase uses rsync's built-in `--info=progress2` display (no `tqdm` installation required), mirrored to the interactive terminal and written to the private `corpora-rsync.log`. It shows approximate cumulative bytes, percentage, transfer rate, and ETA. The first progress update may be delayed while `--no-inc-recursive` builds the complete file list, and rates/ETAs can fluctuate. Resumed transfers show progress against the remaining rsync workload, not necessarily against the original 55 GiB corpus total.

Use a persistent terminal multiplexer such as `tmux` for long SSH sessions; disconnecting an ordinary SSH terminal may interrupt the backup. Progress logs can contain corpus paths or rsync errors, so keep them private.

## Files and security

The new destination is `0700`; the manifest and private reports are `0600`. Typical contents:

```text
<BACKUP>/
  manifest.json                  # image ID, corpus bind source, completion flags, SHA-256
  artifacts/
    original-image.tar.gz        # docker image save by immutable image ID
    bonito.tar.gz                # docker cp /var/lib/bonito, tar stream
    container-rootfs-export.tar.gz # docker export; excludes mounted corpora
    host-nginx.tar.gz            # /etc/nginx, if present
  private/
    container-inspect.json       # SENSITIVE: includes environment values
    image-inspect.json
    docker-diff.txt              # added, changed and removed container paths
    deployment/                  # checkout (including possible .env and secrets), NOT corpora
    deployment-rsync.log
  corpora/                       # complete host /corpora bind source copied by rsync
  corpora-rsync.log
  live-compare-rsync.log         # optional, may disclose corpus paths
```

**The image alone does NOT include the live writable layer; `docker export` is NOT an image and excludes mounted volumes.** The rootfs export provides a forensic copy of the merged container filesystem, while `bonito.tar.gz` independently preserves vulnerable state. Reconstruction of modifications from the export and `docker-diff.txt` is a manual, test-only procedure; do not blindly import or deploy a rootfs export.

The raw inspect, Nginx archive, Bonito files, deployment checkout and rootfs export may contain **authentication secrets and private keys**. Backups must never be committed or uploaded unencrypted. Restrict access and retain an encrypted off-host copy under LNB policy. Host-managed wildcard TLS private keys located outside `/etc/nginx` are **not automatically included**: have IT verify their existing protected backup separately.

The `manifest.json` includes SHA-256 hashes and byte counts for compressed archives. It does not store an exhaustive hash of every corpus file; `verify --compare-live` performs a full checksum comparison against the current source, so later changes to that source may produce legitimate differences. Verification is not a substitute for a filesystem snapshot or a test restore. On a live database-like workload, plan a quiesced or snapshotted final pass separately.

## Abort and acceptance criteria

Stop immediately on unexpected mount mappings, nested mounts, an image change, missing state, insufficient destination storage, changed image ID during a resumed phase, or errors in rsync/checksum verification. In these cases, **do not modify production** to make the script succeed; investigate and document the discrepancy.

A successful backup requires both phases marked complete, verified archive hashes, satisfactory corpus parity, a second independent copy, and a successful **isolated** restoration per [RESTORE.md](RESTORE.md). No restart, `docker stop`, `docker rm`, `docker compose up`, `docker commit`, or recompilation commands are invoked by these scripts.
