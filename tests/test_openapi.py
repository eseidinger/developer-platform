import json
import sys
import unittest
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "platform"))
from app.main import app


class OpenApiContract(unittest.TestCase):
    def test_committed_contract_matches_the_application(self):
        committed = json.loads((root / "docs" / "api" / "openapi.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, json.loads(json.dumps(app.openapi())),
                         "run scripts/export_openapi.py to refresh docs/api/openapi.json")

    def test_put_accepts_the_envelope_and_the_flat_body(self):
        schema = app.openapi()["paths"]["/projects/{name}"]["put"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual({item["$ref"].rsplit("/", 1)[1] for item in schema["anyOf"]},
                         {"ApplicationEnvelope", "Project"})


if __name__ == "__main__":
    unittest.main()
