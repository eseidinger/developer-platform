import base64
from datetime import datetime, timedelta, timezone
import os
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request
from app.stores import catalog, dashboards


class DashboardsBridgeTests(TestCase):
    def setUp(self):
        self.environ = patch.dict(os.environ, {'OPENSEARCH_DASHBOARDS_IP': '172.30.80.31',
            'OPENSEARCH_IP': '172.30.80.17', 'OPENSEARCH_CA_FILE': '/public/ca.pem',
            'STORE_RELAY_IP': '172.30.80.15'})
        self.environ.start(); self.addCleanup(self.environ.stop)
        self.cid = uuid4()
        self.row = {'credential_id': str(self.cid), 'provider': 'opensearch', 'kind': 'human',
            'relay_port': 20000, 'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)}

    def request(self, user=None, selected=True, source='172.30.80.31', extra=()):
        auth = 'Basic ' + base64.b64encode(((user or catalog.login(self.cid)) + ':native-password').encode()).decode()
        headers = [(b'host', dashboards.HOST.encode()), (b'authorization', auth.encode()), *extra]
        if selected: headers.append((dashboards.HEADER.encode(), str(self.cid).encode()))
        return Request({'type': 'http', 'method': 'GET', 'path': '/_search', 'raw_path': b'/_search',
            'query_string': b'', 'headers': headers, 'client': (source, 12345)})

    def test_matching_human_uses_only_its_native_lease_and_never_an_operator_key(self):
        target, verify, row = dashboards.native_target(self.request(), lambda cid: self.row if cid == self.cid else None)
        self.assertEqual(target, 'http://172.30.80.15:20000')
        self.assertTrue(verify)
        self.assertEqual(row, self.row)

    def test_foreign_login_cannot_borrow_the_launched_human_lease(self):
        with self.assertRaises(HTTPException) as denied:
            dashboards.native_target(self.request(user=catalog.login(uuid4())), lambda cid: self.row)
        self.assertEqual(denied.exception.status_code, 403)

    def test_expired_revoked_nonhuman_wrong_provider_and_invalid_port_are_denied(self):
        for row in (None, {**self.row, 'kind': 'application'}, {**self.row, 'provider': 's3'},
                {**self.row, 'relay_port': 9200},
                {**self.row, 'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}):
            with self.assertRaises(HTTPException):
                dashboards.native_target(self.request(), lambda cid: row)

    def test_only_fixed_console_service_can_call_bridge_and_forwarded_source_is_ignored(self):
        for source in ('172.30.80.20', '127.0.0.1'):
            request = self.request(source=source, extra=((b'x-forwarded-for', b'172.30.80.31'),))
            with self.assertRaises(HTTPException):
                dashboards.native_target(request, lambda cid: self.row)

    def test_server_identity_has_no_human_header_and_retains_verified_native_tls(self):
        target, verify, row = dashboards.native_target(self.request(user='kibanaserver', selected=False), lambda cid: None)
        self.assertEqual((target, verify, row), ('https://172.30.80.17:9200', '/public/ca.pem', None))
        for request in (self.request(user='admin', selected=False), self.request(user='kibanaserver'), self.request(selected=False)):
            with self.assertRaises(HTTPException): dashboards.native_target(request, lambda cid: self.row)

    def test_duplicate_authentication_and_upgrade_are_denied(self):
        for extra in (((b'authorization', b'Basic invalid'),), ((b'upgrade', b'websocket'),)):
            with self.assertRaises(HTTPException):
                dashboards.native_target(self.request(extra=extra), lambda cid: self.row)

    def test_login_page_server_metadata_read_still_requires_its_active_human_lease(self):
        request = self.request(user='kibanaserver')
        request.scope.update(path='/_plugins/_security/dashboardsinfo', raw_path=b'/_plugins/_security/dashboardsinfo')
        self.assertEqual(dashboards.native_target(request, lambda cid: self.row)[0], 'https://172.30.80.17:9200')
        with self.assertRaises(HTTPException): dashboards.native_target(request, lambda cid: None)
        request.scope['method'] = 'POST'
        with self.assertRaises(HTTPException): dashboards.native_target(request, lambda cid: self.row)

    def test_anonymous_native_login_settings_are_preserved_only_for_a_launched_lease(self):
        request = self.request()
        request.scope.update(path='/_plugins/_security/dashboardsinfo', raw_path=b'/_plugins/_security/dashboardsinfo')
        request.scope['headers'] = [(key, value) for key, value in request.scope['headers'] if key != b'authorization']
        self.assertEqual(dashboards.native_target(request, lambda cid: self.row)[0], 'https://172.30.80.17:9200')
        with self.assertRaises(HTTPException): dashboards.native_target(request, lambda cid: None)
        request.scope['raw_path'] = b'/_search'
        with self.assertRaises(HTTPException): dashboards.native_target(request, lambda cid: self.row)
