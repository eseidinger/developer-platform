import json
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "platform" / "app" / "src"))
from app.main import app


class OpenApiContract(unittest.TestCase):
    def test_committed_contract_matches_the_application(self):
        committed = json.loads(
            (root / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            committed,
            json.loads(json.dumps(app.openapi())),
            "run scripts/generate/export_openapi.py to refresh docs/api/openapi.json",
        )

    def test_put_accepts_only_the_v1_declaration(self):
        schema = app.openapi()["paths"]["/projects/{name}"]["put"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(schema, {"$ref": "#/components/schemas/ApplicationEnvelope"})


if __name__ == "__main__":
    unittest.main()
