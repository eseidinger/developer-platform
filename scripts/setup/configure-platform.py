#!/usr/bin/env python3
"""Validate local .env settings or apply settings supplied by Ansible on stdin."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.internal.deployment_options import ConfigurationError
from scripts.internal.platform_configuration import configure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read Ansible configuration as JSON from stdin",
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate without writing files"
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Honor environment overrides used by bootstrap",
    )
    args = parser.parse_args()
    specification = {}
    try:
        if args.stdin:
            specification = json.load(sys.stdin)
        changed = configure(
            Path(__file__).resolve().parents[2],
            specification,
            check=args.check,
            runtime=args.runtime,
        )
    except (ConfigurationError, OSError, ValueError):
        # Parsing errors can embed raw configuration; never forward their text.
        print(
            "Platform configuration failed; check the documented settings and private files.",
            file=sys.stderr,
        )
        return 1
    print(
        "Platform configuration "
        + ("validated." if args.check or not changed else "updated.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
