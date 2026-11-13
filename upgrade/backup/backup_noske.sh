#!/usr/bin/env bash
# No action without --execute. Never stop, remove, or restart Docker objects.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/backup_noske.py" backup "$@"
