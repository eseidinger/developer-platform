#!/usr/bin/env python3
"""Plan or run the scoped named PostgreSQL and network isolation drill."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from acceptance.isolation import main

if __name__ == "__main__":
    raise SystemExit(main())
