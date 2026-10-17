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

    def test_broken_native_admin_does_not_repeat_cleanup_for_every_generation(self):
        from app.stores import worker
        from unittest.mock import MagicMock
        bad,good=str(uuid4()),str(uuid4())
        rows=[({'credential_id':str(uuid4())},{'resource_id':rid,'provider':'neo4j'}) for rid in (bad,bad,good)]
        attempted=[]
        def deny(conn,credential,resource):
            attempted.append(resource['resource_id'])
            if resource['resource_id']==bad:raise ValueError('private-marker')
        connection=MagicMock()
        with patch.object(worker,'_deny',side_effect=deny):worker.deny_stale(connection,rows)
        self.assertEqual(attempted,[bad,good])
        self.assertNotIn('private-marker',str(connection.execute.call_args_list))

    def test_recreated_infrastructure_rejoins_only_owned_running_instance_networks(self):
        from app.stores.neo4j import IMAGE
        rid=uuid4();name,_,network=names(rid)
        engine=Mock();calls=[]
        def call(method,path,body=None,missing=False):
            calls.append((method,path,body))
            if path=='/containers/json?all=1':return [{'Names':['/'+name],'Labels':{LABEL:str(rid)}}]
            if path=='/containers/'+name+'/json':return {'Config':{'Labels':{LABEL:str(rid)},'Image':IMAGE},'State':{'Running':True}}
            if path=='/networks/'+network:return {'Labels':{LABEL:str(rid)},'Internal':True}
            if path=='/containers/new-api/json':return {'State':{'Running':True},'NetworkSettings':{'Networks':{}}}
            return None
        engine.call.side_effect=call
        with patch.dict(os.environ,{'NEO4J_NETWORK_MEMBERS':'new-api,not-created-yet'}):Controller(engine).reconcile_networks()
        self.assertIn(('POST','/networks/'+network+'/connect',{'Container':'new-api'}),calls)
        self.assertFalse(any(path.endswith('/start') for _,path,_ in calls))

    def test_discovery_explicitly_reports_full_instance_access_without_read_only(self):
        values=providers.capabilities('neo4j')
        self.assertEqual(values['supported_modes'],['read-write'])
        self.assertEqual(values['access_model'],'full-instance')
        self.assertTrue(values['native_account_management'])
        self.assertFalse(providers.capabilities('postgresql')['native_account_management'])

    def test_invalid_controller_address_is_unavailable(self):
        with patch.dict(os.environ,{'STORE_ENABLED_PROVIDERS':'neo4j','NEO4J_CONTROLLER_IP':'invalid'}),self.assertRaises(providers.ProviderUnavailable):
            providers.get('neo4j')
