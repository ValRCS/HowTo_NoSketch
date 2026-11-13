# Restore drill and rollback gate — NoSketch Engine

**Do not run restore commands against production until a separately reviewed migration/rollback change has been authorized.** This document defines a drill on an isolated host, not an automatic restore script. The live `noske` container may be configured `AutoRemove=true`, so a stop can permanently remove its writable layer.

## 1. Validate sources and isolation

1. Obtain the approved, private backup on a **different** test host or secured test volume. Verify archive SHA-256 (`verify_backup.py --destination ...`) and check `manifest.json`: `state_complete` and `corpora_complete` must both be true.
2. Confirm the original image ID and architecture from `private/image-inspect.json`. Check that `private/container-inspect.json` identifies the expected original ports, environment variable **names**, network, mounts and container entrypoint. Do not print or share secret values.
3. Use a private test network. **Never bind public production ports or mount the production corpus path.** Use only backed-up corpora, initially mounted read-only for query tests; grant write access only to an isolated copy if needed for functionality.
4. Review `private/docker-diff.txt` (A/C/D entries) to identify runtime changes, especially Bonito state, Apache, Crystal, Shibboleth and authentication. The full rootfs export is reference material for a controlled, minimal reconstruction. It does not replace the original Docker image or the corpus backup.
5. Identify any external secret sources, protected wildcard TLS key backups and symlink targets that were not captured. Confirm consistency of snapshot/copy dates and whether any live writes occurred during backup.

## 2. Isolated reconstruction

- On the test host, import `original-image.tar.gz` using a controlled `docker load` operation. Verify the imported image matches the recorded immutable image ID.
- Extract backed-up corpora to an **isolated test directory**, preserving file ownership, modes, ACLs and extended attributes. Review symlinks, nested mount exceptions and UID/GID mappings.
- Reconstruct launch settings from the restricted inspect/deployment backup (not from today's upstream Compose defaults). Recreate required state from `bonito.tar.gz` and the *reviewed* changed paths from the rootfs export. Any restored authentication or certificate material must remain private and appropriately protected.
- Start a **separate**, non-public test container on an unused loopback port without `--rm`. Do not start Traefik or alter production Nginx. Avoid running the upstream Makefile's `run`, `clean` or `compile` targets.
- Verify the original image/Bonito combination starts, corpora register correctly, representative concordance and metadata queries work, and compiled indexes are usable **without recompilation**. Inspect server logs without publishing secrets.
- Test the restore *twice*: from the primary local copy and from the independent off-host copy, or otherwise independently validate second-copy integrity.

## 3. Record and decision gate

Document: backup location (private), timestamps, manifest hashes, container image ID, directory counts, test commands (redacted), corpus sample queries/results, restoration duration, differences, remaining unknowns and IT sign-off. Keep reports and secrets outside the public repo.

**Rollback is not certified** until the complete original deployment can be reconstructed and queried on isolated storage without modifying production. Any proposed production upgrade must include an explicit rollback command sequence reviewed against actual current mounts, host proxy configuration and the tested restore artifacts. A failed test blocks the upgrade.
