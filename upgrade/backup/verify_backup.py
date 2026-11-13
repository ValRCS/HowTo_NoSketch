#!/usr/bin/env python3
"""Verify private backup archive checksums and optional live corpora parity."""
import sys
from backup_noske import main

if __name__ == "__main__":
    sys.exit(main(["verify", *sys.argv[1:]]))
