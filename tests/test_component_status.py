import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app.component_status import next_run, observe_components


NOW = datetime(2026, 10, 4, 12, 7, tzinfo=timezone.utc)


class ComponentStatusTests(unittest.TestCase):
    def test_next_run_uses_utc_five_field_schedule(self):
        self.assertEqual(next_run("*/15 * * * *", NOW), "2026-10-04T12:15:00+00:00")
        self.assertEqual(next_run("0 13 * * *", NOW), "2026-10-04T13:00:00+00:00")

    def test_observes_service_and_scheduled_component(self):
        runtime, log = Mock(), Mock()
        cronjobs = Mock()
        runtime.resources.get.side_effect = lambda **kwargs: cronjobs if kwargs["kind"] == "CronJob" else Mock()
        cronjobs.get.return_value = {"status": {"active": [{"name": "worker-1"}],
                                                   "lastScheduleTime": "2026-10-04T12:00:00Z",
                                                   "lastSuccessfulTime": "2026-10-04T11:45:02Z"}}
        components = [
            {"name": "api", "type": "service", "resolved_image": "registry/api@sha256:one"},
            {"name": "worker", "type": "scheduled", "schedule": "*/15 * * * *"},
        ]
        readiness = {"state": "ready"}
        with patch("app.component_status.observe_deployment", return_value=readiness) as observe:
            result = observe_components(runtime, "shop", components, log, NOW)

        self.assertEqual(result["components"][0], {"name": "api", "type": "service", "status": readiness})
        scheduled = result["components"][1]
        self.assertEqual(scheduled["state"], "active")
        self.assertEqual(scheduled["next_run"], "2026-10-04T12:15:00+00:00")
        self.assertEqual(scheduled["active_runs"], 1)
        self.assertEqual(scheduled["last_result"], "succeeded")
        observe.assert_called_once_with(runtime, "shop", "registry/api@sha256:one", log, "api")

    def test_missing_cronjob_is_reported_without_failure_detail(self):
        runtime, log = Mock(), Mock()
        cronjobs = Mock()
        runtime.resources.get.return_value = cronjobs
        from kubernetes.client.exceptions import ApiException
        cronjobs.get.side_effect = ApiException(status=404)
        result = observe_components(runtime, "shop", [{"name": "worker", "type": "scheduled",
                                    "schedule": "0 * * * *"}], log, NOW)["components"][0]
        self.assertEqual((result["state"], result["reason"], result["failure"]),
                         ("not_found", "CronJobNotFound", None))

    def test_failed_job_exposes_only_the_safe_kubernetes_reason(self):
        runtime, log = Mock(), Mock()
        cronjobs, jobs = Mock(), Mock()
        runtime.resources.get.side_effect = lambda **kwargs: cronjobs if kwargs["kind"] == "CronJob" else jobs
        cronjobs.get.return_value = {"status": {"lastScheduleTime": "2026-10-04T12:00:00Z"}}
        jobs.get.return_value = {"items": [{"status": {"completionTime": "2026-10-04T12:01:00Z",
            "conditions": [{"type": "Failed", "status": "True", "reason": "BackoffLimitExceeded",
                            "message": "password=should-not-leak"}]}}]}
        result = observe_components(runtime, "shop", [{"name": "worker", "type": "scheduled",
                                    "schedule": "0 * * * *"}], log, NOW)["components"][0]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["failure"], {"reason": "BackoffLimitExceeded"})
        self.assertNotIn("should-not-leak", str(result))
        jobs.get.assert_called_once_with(namespace="project-shop", label_selector="platform.example/component=worker")


if __name__ == "__main__":
    unittest.main()
