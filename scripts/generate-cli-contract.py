#!/usr/bin/env python3
"""Generate/check the CLI's packaged public API contract without importing FastAPI."""

import argparse
import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
source = json.loads((root / "docs/api/openapi.json").read_text())
contract = {"paths": source["paths"], "components": source["components"], "openapi": source["openapi"]}
target = root / "platform/cli/src/platform_cli/api_contract.json"
rendered = json.dumps(contract, indent=2, sort_keys=True) + "\n"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
if args.check:
    if not target.exists() or target.read_text() != rendered:
        parser.exit(1, "CLI API contract is stale; run scripts/generate-cli-contract.py.\n")
else:
    target.write_text(rendered)
