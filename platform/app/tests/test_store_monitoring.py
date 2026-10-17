"""Unknown usage, stale measurements, and provider failures must remain visible."""
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch
from app.stores import monitoring


class StoreMonitoringTests(TestCase):
    def test_unknown_is_absent_but_measured_zero_is_preserved_and_error_separate(self):
        rows = [dict(resource_id='a', owner_project='alpha', provider='postgresql', quota_bytes=1024,
            state='active', observed_state='active', used_bytes=None, usage_error=True),
            dict(resource_id='b', owner_project='beta', provider='s3', quota_bytes=1024,
            state='retired', observed_state='retired', used_bytes=0,
            usage_measured_at=datetime.fromtimestamp(50, timezone.utc), usage_error=False)]
        content = monitoring.exposition(rows, [{'resource_id': 'a', 'active': 1, 'cleanup': 2}], now=100)
        self.assertNotIn('platform_store_used_bytes{project="alpha"', content)
        self.assertIn('platform_store_used_bytes{project="beta",resource_id="b",provider="s3"} 0', content)
        self.assertIn('platform_store_usage_error{project="alpha",resource_id="a",provider="postgresql"} 1', content)
        self.assertIn('platform_store_credentials_cleanup_pending{project="alpha",resource_id="a",provider="postgresql"} 2', content)
        self.assertIn('platform_store_worker_last_success_timestamp_seconds 100', content)
        self.assertNotIn('password', content)

    def test_failed_measurement_retains_previous_usage_and_another_store_can_succeed(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [({'resource_id': 'bad', 'provider': 'postgresql'},),
            ({'resource_id': 'good', 'provider': 'postgresql'},)]
        provider = Mock()
        provider.usage.side_effect = [RuntimeError('private provider diagnostic'), 123]
        with patch.object(monitoring.providers, 'get', return_value=provider):
            monitoring.sample(conn)
        statements = conn.execute.call_args_list
        self.assertNotIn('used_bytes=', statements[1].args[0])
        self.assertIn('usage_error=true', statements[1].args[0])
        self.assertEqual(statements[2].args[1], (123, 'good'))
        self.assertNotIn('private provider diagnostic', str(statements))
