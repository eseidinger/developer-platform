#!/usr/bin/env python3
"""Run the synthetic AI incident corpus with the configured eligible model."""

import json
import argparse
from pathlib import Path

from app.ai_evaluation import evaluate, CASES, LEGACY_CASES
from app.ai_model import configured_model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=("current", "legacy"), default="current")
    parser.add_argument("--progress", action="store_true", help="Print score-only per-case progress")
    parser.add_argument("--report-file", type=Path, help="Write a score-only JSON report")
    args = parser.parse_args()
    report = evaluate(configured_model(), CASES if args.corpus == "current" else LEGACY_CASES,
                      on_case=(lambda result: print(json.dumps(result), flush=True)) if args.progress else None)
    if args.report_file:
        args.report_file.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if (report["known_cause_accuracy"] >= 0.8
                           and report["insufficient_evidence_abstention"]
                           and report["budget_compliant"]) else 1)
