import logging
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from kubernetes.client.exceptions import ApiException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.logs import MAX_LINE_CHARS, MAX_PODS, observe_logs

NOW = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
log = logging.getLogger("test")


def pod(name, *containers):
    return {"metadata": {"name": name}, "spec": {"containers": [{"name": c} for c in containers or ("app",)]}}


def setup(pods, outputs=None, error=None):
    runtime = Mock()
    runtime.resources.get.return_value.get.return_value = {"items": pods}
    api = Mock()
    if error is not None:
        api.read_namespaced_pod_log.side_effect = error
    else:
        api.read_namespaced_pod_log.side_effect = lambda name, namespace, **kw: (outputs or {})[(name, kw["container"])]
    return runtime, api


class LogTests(unittest.TestCase):
    def test_lines_are_attributed_ordered_and_trimmed_to_the_tail(self):
        runtime, api = setup([pod("a"), pod("b")], {
            ("a", "app"): "2026-10-03T11:00:01.000000000Z first\n2026-10-03T11:00:03.000000000Z third\n",
            ("b", "app"): "2026-10-03T11:00:02.000000000Z second\n"})
        result = observe_logs(runtime, "smoke", log, tail=2, since_seconds=None, api=api, now=NOW)
        self.assertEqual(result["state"], "ok")
        self.assertEqual([(l["pod"], l["container"], l["message"]) for l in result["lines"]],
                         [("b", "app", "second"), ("a", "app", "third")])
        self.assertEqual(result["lines"][0]["timestamp"], "2026-10-03T11:00:02.000000000Z")
        self.assertEqual(result["truncated"], True)
        runtime.resources.get.assert_called_with(api_version="v1", kind="Pod")
        runtime.resources.get.return_value.get.assert_called_with(
            namespace="project-smoke", label_selector="app.kubernetes.io/name=smoke")
        kwargs = api.read_namespaced_pod_log.call_args.kwargs
        self.assertEqual((kwargs["tail_lines"], kwargs["timestamps"], kwargs["limit_bytes"]), (2, True, 262144))
        self.assertNotIn("since_seconds", kwargs)

    def test_since_window_is_passed_to_the_log_api(self):
        runtime, api = setup([pod("a")], {("a", "app"): ""})
        observe_logs(runtime, "smoke", log, tail=10, since_seconds=300, api=api, now=NOW)
        self.assertEqual(api.read_namespaced_pod_log.call_args.kwargs["since_seconds"], 300)

    def test_credentials_are_redacted_and_long_lines_capped(self):
        long = "x" * (MAX_LINE_CHARS + 50)
        runtime, api = setup([pod("a")], {("a", "app"):
            "2026-10-03T11:00:01Z Authorization: Bearer abc.def.ghi\n2026-10-03T11:00:02Z password=hunter2\n"
            "2026-10-03T11:00:03Z " + long + "\n"})
        lines = observe_logs(runtime, "smoke", log, tail=10, since_seconds=None, api=api, now=NOW)["lines"]
        self.assertNotIn("abc.def.ghi", lines[0]["message"])
        self.assertNotIn("hunter2", lines[1]["message"])
        self.assertEqual(len(lines[2]["message"]), MAX_LINE_CHARS)

    def test_no_pods_and_no_output_are_labelled(self):
        runtime, api = setup([])
        self.assertEqual(observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)["state"], "no_pods")
        runtime, api = setup([pod("a")], {("a", "app"): ""})
        result = observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)
        self.assertEqual((result["state"], result["lines"]), ("no_output", []))

    def test_waiting_container_falls_back_to_previous_logs_then_is_reported(self):
        runtime, api = setup([pod("a")])

        def read(name, namespace, **kw):
            if kw.get("previous"):
                return "2026-10-03T11:00:01Z crashed: boom\n"
            raise ApiException(status=400)
        api.read_namespaced_pod_log.side_effect = read
        result = observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)
        self.assertEqual(result["lines"][0]["message"], "crashed: boom")
        self.assertTrue(result["lines"][0]["previous"])
        api.read_namespaced_pod_log.side_effect = ApiException(status=400)
        result = observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)
        self.assertEqual((result["state"], result["unavailable_containers"]), ("no_output", 1))

    def test_all_log_reads_failing_is_unavailable_without_details(self):
        runtime, api = setup([pod("a")], error=ApiException(status=500))
        result = observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)
        self.assertEqual((result["state"], result["reason"]), ("unavailable", "LogApiUnavailable"))
        runtime = Mock()
        runtime.resources.get.return_value.get.side_effect = RuntimeError("secret detail")
        result = observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=Mock(), now=NOW)
        self.assertEqual(result["state"], "unavailable")
        self.assertNotIn("secret", str(result))
        self.assertEqual(observe_logs(None, "smoke", log, tail=5, since_seconds=None, now=NOW)["state"], "unavailable")

    def test_pod_count_is_bounded(self):
        pods = [pod("p%02d" % i) for i in range(MAX_PODS + 5)]
        runtime, api = setup(pods, {(p["metadata"]["name"], "app"): "" for p in pods})
        observe_logs(runtime, "smoke", log, tail=5, since_seconds=None, api=api, now=NOW)
        self.assertEqual(api.read_namespaced_pod_log.call_count, MAX_PODS)


if __name__ == "__main__":
    unittest.main()
