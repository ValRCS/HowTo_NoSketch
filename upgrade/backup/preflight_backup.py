#!/usr/bin/env python3
"""Read-only backup preflight; see README.md."""
import sys
from backup_noske import main

if __name__ == "__main__":
    sys.exit(main(["preflight", *sys.argv[1:]]))
