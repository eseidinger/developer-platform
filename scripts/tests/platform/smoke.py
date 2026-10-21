#!/usr/bin/env python3
"""Plan or run scoped smoke checks; retire only the newly created fixture project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform"))
from acceptance.lifecycle.runner import main

if __name__ == "__main__":
    raise SystemExit(main(smoke=True))
