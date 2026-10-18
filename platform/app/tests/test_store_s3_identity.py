from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4
from botocore.exceptions import ClientError
from app.stores.s3 import S3, StoreError


class S3CredentialOwnershipTests(TestCase):
    def test_cleanup_cannot_delete_a_colliding_foreign_service_account(self):
        provider = S3.__new__(S3)
        provider.admin = Mock(return_value={'parentUser': 'a-different-managed-parent'})
        with self.assertRaises(StoreError):
            provider.revoke({'resource_id': str(uuid4())}, {'credential_id': str(uuid4())})
        self.assertEqual(provider.admin.call_count, 1)
        self.assertEqual(provider.admin.call_args.args[:2], ('GET', 'info-service-account'))

    def test_revocation_waits_for_native_denial_and_fails_closed_if_key_stays_live(self):
        provider = S3.__new__(S3)
        provider.endpoint = 'http://fixture.invalid'
        provider.root = Mock()
        provider.admin = Mock(return_value=None)
        resource = {'resource_id': str(uuid4())}
        credential = {'credential_id': str(uuid4())}
        denied = ClientError({'Error': {'Code': 'InvalidRequest'},
            'ResponseMetadata': {'HTTPStatusCode': 400}}, 'ListObjectsV2')
        scoped = Mock()
        with patch('app.stores.s3.client', return_value=scoped), \
                patch('app.stores.s3.catalog.secret_for', return_value='secret'), \
                patch('app.stores.s3.time.sleep'):
            scoped.list_objects_v2.side_effect = [{}, denied]
            provider.revoke(resource, credential)
            self.assertEqual(scoped.list_objects_v2.call_count, 2)
            scoped.list_objects_v2.reset_mock(side_effect=True)
            scoped.list_objects_v2.return_value = {}
            with self.assertRaisesRegex(StoreError, 'remains active'):
                provider.revoke(resource, credential)
            self.assertEqual(scoped.list_objects_v2.call_count, 20)
