import os
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.stores.neo4j_controller import Controller, create_app, names, LABEL
from app.stores import providers, catalog


class ControllerBoundaryTests(TestCase):
    def setUp(self):
        self.control=Mock()
        self.environment=patch.dict(os.environ,{'NEO4J_CONTROLLER_KEY':'a'*64,'NEO4J_ADMIN_KEY':'b'*64,'PLATFORM_API_IP':'testclient'})
        self.environment.start();self.addCleanup(self.environment.stop)
        self.client=TestClient(create_app(self.control))
        self.path='/v1/instances/'+str(uuid4())+'/ensure'
        self.headers={'Authorization':'Bearer '+'a'*64}

    def test_invalid_key_and_wrong_source_never_reach_controller(self):
        self.assertEqual(self.client.post(self.path,json={}).status_code,403)
        with patch.dict(os.environ,{'PLATFORM_API_IP':'172.30.80.11'}):
            self.assertEqual(self.client.post(self.path,json={},headers=self.headers).status_code,403)
        self.control.apply.assert_not_called()

    def test_arbitrary_command_and_oversized_payload_are_not_accepted(self):
        for payload,status in [({'command':'docker privileged'},503),({'password':'x'*5000},413),([],503)]:
            self.assertEqual(self.client.post(self.path,json=payload,headers=self.headers).status_code,status)
        self.control.apply.assert_not_called()

    def test_native_error_diagnostics_are_not_returned(self):
        self.control.apply.side_effect=ValueError('private-marker')
        response=self.client.post(self.path,json={},headers=self.headers)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private-marker',response.text)

    def test_unknown_resource_names_cannot_target_host_paths(self):
        with self.assertRaises(ValueError):names('../host')

    def test_unknown_network_member_blocks_purge_before_mutation(self):
        rid=uuid4();engine=Mock();engine.call.return_value={'Labels':{LABEL:str(rid)},'Internal':True,'Containers':{'foreign':{}}}
        controller=Controller(engine)
        with patch.dict(os.environ,{'NEO4J_NETWORK_MEMBERS':''}),self.assertRaises(ValueError):
            controller.purge_network(rid,{'Id':'owned'})
        self.assertTrue(all(call.args[0]=='GET' for call in engine.call.call_args_list))

    def test_foreign_volume_is_never_deleted(self):
        rid=uuid4();engine=Mock();controller=Controller(engine)
        with patch.object(controller,'info',return_value=None),patch.object(controller,'purge_network'), \
                self.assertRaises(ValueError):
            engine.call.return_value={'Labels':{LABEL:str(uuid4())}}
            controller.apply(rid,'purge',{})
        self.assertFalse(any(call.args[0]=='DELETE' for call in engine.call.call_args_list))

    def test_instance_admission_counts_retained_resources(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=(4,)
        with patch.dict(os.environ,{'NEO4J_MAX_INSTANCES':'4'}),self.assertRaises(catalog.Conflict):
            providers.check_capacity(conn,'neo4j',1024)

    def test_rpc_key_rotation_does_not_change_native_admin_password(self):
        controller=Controller(Mock());rid=uuid4()
        original=controller.password(rid)
        with patch.dict(os.environ,{'NEO4J_CONTROLLER_KEY':'c'*64}):self.assertEqual(controller.password(rid),original)

    def test_retired_identity_cleanup_uses_instance_stop_without_native_admin_login(self):
        from app.stores.neo4j import Neo4j
        provider=Neo4j(key='a'*64)
        with patch.object(provider,'call') as call:
            provider.revoke({'resource_id':str(uuid4()),'state':'retired'},{'credential_id':str(uuid4())})
        self.assertEqual(call.call_args.args[0],'retire')

    def test_invalid_controller_address_is_unavailable(self):
        with patch.dict(os.environ,{'STORE_ENABLED_PROVIDERS':'neo4j','NEO4J_CONTROLLER_IP':'invalid'}),self.assertRaises(providers.ProviderUnavailable):
            providers.get('neo4j')
