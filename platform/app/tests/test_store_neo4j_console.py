from datetime import datetime,timedelta,timezone
import os
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Host
from starlette.websockets import WebSocketDisconnect
from app.stores import console
from app.stores.api import reply


class Neo4jConsoleBoundaryTests(TestCase):
    def setUp(self):
        self.settings=patch.dict(os.environ,{'DATABASE_KEY':'a'*64,'APPS_DOMAIN':'apps.fixture.test','STORE_RELAY_IP':'127.0.0.1'})
        self.settings.start();self.addCleanup(self.settings.stop)
        self.row={'credential_id':str(uuid4()),'resource_id':str(uuid4()),'provider':'neo4j','kind':'human','relay_port':20000,
            'expires_at':datetime.now(timezone.utc)+timedelta(hours=24),'issuer':'https://identity.fixture.test','subject':'fixture-human'}
        self.load=Mock(return_value=self.row)
        app=FastAPI();app.router.routes.append(Host('console-{port:int}.apps.fixture.test',app=console.create_gateway(self.load)))
        self.client=TestClient(app)
        self.cookie=console.assertion(self.row,'session',86400)

    def attempt(self,**headers):
        values={'origin':console.origin(20000),'cookie':console.COOKIE+'='+self.cookie,**headers}
        with patch('app.stores.console.asyncio.open_connection') as connection, self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('wss://console-20000.apps.fixture.test/',headers=values):pass
        connection.assert_not_called()

    def test_foreign_origin_and_unreviewed_subprotocol_are_rejected_before_tcp(self):
        self.attempt(origin='https://foreign.fixture.test')
        self.load.assert_not_called()
        self.attempt(**{'sec-websocket-protocol':'arbitrary-tunnel'})
        self.load.assert_not_called()

    def test_other_provider_and_expired_lease_cannot_open_bolt_socket(self):
        self.row['provider']='qdrant';self.attempt()
        self.row['provider']='neo4j';self.row['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1);self.attempt()

    def test_missing_or_wrong_launch_cookie_cannot_open_tcp(self):
        self.attempt(cookie='')
        self.attempt(cookie=console.COOKIE+'=invalid')

    def test_admission_verifier_is_not_in_public_credential_replies(self):
        response=reply({'credential_id':'public','admission_sha256':'private-marker',
            'nested':[{'admission_sha256':'private-marker','connection':{'NEO4J_PASSWORD':'explicit-secret'}}]})
        self.assertNotIn(b'private-marker',response.body)
        self.assertIn(b'explicit-secret',response.body)
