#!/usr/bin/env bash
# Convenience launcher. Only runs read-only inventory queries.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/inventory_noske.py" "$@"
