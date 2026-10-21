#!/usr/bin/env python3
"""Plan or run the scoped human PostgreSQL acceptance drill."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "platform"))
from acceptance.human_database import main

if __name__ == "__main__":
    raise SystemExit(main())
