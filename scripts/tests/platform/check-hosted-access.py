#!/usr/bin/env python3
"""Domain-neutral hosted-access acceptance; defaults to a non-mutating plan."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "platform" / "app" / "src"))
sys.path.insert(0, str(root / "platform"))
from acceptance.harness import main

if __name__ == "__main__":
    raise SystemExit(main())
