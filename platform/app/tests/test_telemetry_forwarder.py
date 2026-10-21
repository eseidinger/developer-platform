import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "telemetry_forwarder.py"
spec = importlib.util.spec_from_file_location("telemetry_forwarder", SOURCE)
forwarder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forwarder)


class _Gateway:
    def __init__(self):
        self.headers = []

    def open(self, request, timeout):
        self.headers.append(request.get_header("Authorization"))
        return io.BytesIO(b"")


class TelemetryForwarderTests(unittest.TestCase):
    def test_reads_rotated_pod_token_for_each_batch(self):
        original_file, original_opener = forwarder.TOKEN_FILE, forwarder._opener
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token"
            forwarder.TOKEN_FILE = str(token_file)
            gateway = _Gateway()
            forwarder._opener = gateway
            try:
                for token in ("first-token", "rotated-token"):
                    token_file.write_text(token)
                    handler = object.__new__(forwarder.Handler)
                    handler.path = "/v1/traces"
                    handler.headers = {
                        "Content-Type": "application/x-protobuf",
                        "Content-Length": "1",
                    }
                    handler.rfile = io.BytesIO(b"\x00")
                    replies = []
                    handler._reply = lambda status, body=b"", replies=replies: (
                        replies.append(status)
                    )
                    handler.do_POST()
                    self.assertEqual(replies, [200])
                self.assertEqual(
                    gateway.headers, ["Bearer first-token", "Bearer rotated-token"]
                )
            finally:
                forwarder.TOKEN_FILE, forwarder._opener = original_file, original_opener


if __name__ == "__main__":
    unittest.main()
