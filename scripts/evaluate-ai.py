#!/usr/bin/env python3
"""Run the synthetic AI incident corpus with the configured eligible model."""

import json

from app.ai_evaluation import evaluate
from app.ai_model import configured_model


if __name__ == "__main__":
    report = evaluate(configured_model())
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if (report["known_cause_accuracy"] >= 0.8
                           and report["insufficient_evidence_abstention"]
                           and report["budget_compliant"]) else 1)
