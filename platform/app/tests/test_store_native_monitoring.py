import importlib.util
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4
from app.stores import catalog, native_monitoring as native

ROOT = Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('store_workload_metrics',ROOT/'examples/store-observability/metrics.py')
workload=importlib.util.module_from_spec(spec);spec.loader.exec_module(workload)


class NativeMetricsTests(TestCase):
    def setUp(self):
        self.resource={'resource_id':str(uuid4()),'owner_project':'alpha'}
        self.name=catalog.identifier(self.resource['resource_id'])

    def test_pinned_collection_id_and_histogram_route_mapping(self):
        raw='\n'.join([
            f'collection_points{{id="{self.name}"}} 7',
            f'collection_running_optimizations{{id="{self.name}"}} 1',
            f'rest_responses_total{{collection="{self.name}",method="POST",endpoint="/collections/{{collection_name}}/points/query",status="200"}} 3',
            f'rest_responses_duration_seconds_bucket{{le="+Inf"}} 4'])
        result='\n'.join(native.qdrant_samples(raw,[self.resource]))
        self.assertIn('platform_native_qdrant_collection_points',result)
        self.assertIn(self.resource['resource_id'],result)
        self.assertIn('project="alpha"',result)
        self.assertIn('scope="shared"',result)
        self.assertNotIn(self.name,result)

    def test_unknown_collections_and_unreviewed_attributes_cannot_leak(self):
        raw='\n'.join(['memory_resident_bytes 2','collection_points{id="private-marker"} 12',
            f'collection_points{{id="{self.name}",password="private-marker"}} 12','unreviewed_metric{secret="private-marker"} NaN'])
        result='\n'.join(native.qdrant_samples(raw,[self.resource]))
        self.assertIn('memory_resident_bytes',result)
        self.assertNotIn('private-marker',result)
        self.assertNotIn('password',result)

    def test_nonfinite_value_duplicate_label_and_oversized_response_fail(self):
        for value in ['memory_resident_bytes 1e999', 'memory_resident_bytes{status="1",status="2"} 1', 'a'*2097153]:
            with self.subTest(case=value[:40]),self.assertRaises(ValueError):native.qdrant_samples(value,[self.resource])

    def test_private_container_identity_mapping_uses_catalog_only(self):
        root=Mock();root.call.return_value={'containers':[{'provider':'neo4j','resource_id':self.resource['resource_id'],'running':1,'cpu_seconds_total':3},
            {'provider':'neo4j','resource_id':str(uuid4()),'running':1}]}
        with patch('app.stores.neo4j.Neo4j',return_value=root):result='\n'.join(native.containers([self.resource]))
        self.assertIn('project="alpha"',result)
        self.assertEqual(result.count('platform_native_container_running'),1)

    def test_native_collection_failure_retains_old_sample_and_reports_failure(self):
        control=MagicMock();control.connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[]
        stop=Mock();stop.is_set.side_effect=[False,False,True]
        with patch.dict('os.environ',{'STORE_ENABLED_PROVIDERS':'opensearch','MONITORING_DISCOVERY_DIR':'/unused'}), \
                patch.object(native,'postgres',return_value=[]),patch.object(native,'opensearch',side_effect=[['retained_native_value 9'],ValueError('private-marker')]), \
                patch.object(native,'containers',return_value=[]),patch.object(native.providers,'get'), \
                patch('app.monitoring.atomic_write') as write:
            native.loop(stop,control)
        text=write.call_args.args[1]
        self.assertIn('retained_native_value 9',text)
        self.assertIn('platform_native_collection_up{provider="opensearch"} 0',text)
        self.assertNotIn('private-marker',text)

    def test_empty_installation_prepares_monitoring_once_and_retries_failed_setup(self):
        control=MagicMock();control.connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[]
        stop=Mock();stop.is_set.side_effect=[False,False,False,True]
        provider=Mock();provider.ensure_monitoring.side_effect=[ValueError('private-marker'),None]
        with patch.dict('os.environ',{'STORE_ENABLED_PROVIDERS':'opensearch','MONITORING_DISCOVERY_DIR':'/unused'}), \
                patch.object(native,'postgres',return_value=[]),patch.object(native,'opensearch',return_value=[]) as collect, \
                patch.object(native,'containers',return_value=[]),patch.object(native.providers,'get',return_value=provider), \
                patch('app.monitoring.atomic_write') as write:
            native.loop(stop,control)
        self.assertEqual(provider.ensure_monitoring.call_count,2)
        self.assertEqual(collect.call_count,2)
        collect.assert_called_with(provider,[])
        self.assertIn('platform_native_collection_up{provider="opensearch"} 1',write.call_args.args[1])
        self.assertNotIn('private-marker',write.call_args.args[1])


class WorkloadMetricTests(TestCase):
    def test_operation_histograms_record_errors_without_diagnostics(self):
        metrics=workload.StoreMetrics(uuid4(),'age')
        with metrics.operation('query'):pass
        with self.assertRaises(RuntimeError),metrics.operation('rebuild'):raise RuntimeError('private-marker')
        text=metrics.exposition()
        self.assertIn('outcome="success"',text)
        self.assertIn('outcome="error"',text)
        self.assertNotIn('private-marker',text)
        self.assertIn('le="+Inf"',text)

    def test_arbitrary_operation_and_profile_payloads_are_rejected(self):
        metrics=workload.StoreMetrics(uuid4(),'duckdb')
        with self.assertRaises(ValueError):
            with metrics.operation('SELECT private'):pass
        for fields in [{'query':'private'},{'cpu_seconds':float('nan')},{'spill_bytes':-1}]:
            with self.assertRaises(ValueError):metrics.profile(**fields)

    def test_duckdb_profile_exports_only_allowlisted_numeric_fields(self):
        metrics=workload.StoreMetrics(uuid4(),'duckdb')
        metrics.duckdb_profile({'query_name':'private-marker','children':[{'private':'marker'}],
            'cpu_time':.25,'system_peak_buffer_memory':4096,'rows_returned':12})
        text=metrics.exposition()
        self.assertIn('cpu_seconds',text)
        self.assertIn('peak_memory_bytes',text)
        self.assertNotIn('private',text)
