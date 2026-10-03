#!/usr/bin/env python3
"""Write the platform API contract to docs/api/openapi.json (use --check to verify it is current)."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "platform"))
from app.main import app  # noqa: E402

target = root / "docs" / "api" / "openapi.json"
text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
if "--check" in sys.argv:
    if not target.exists() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
        raise SystemExit("docs/api/openapi.json is stale; run scripts/export_openapi.py")
else:
    target.write_text(text, encoding="utf-8", newline="\n")
