from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from app.stores.s3 import S3, StoreError


class S3CredentialOwnershipTests(TestCase):
    def test_cleanup_cannot_delete_a_colliding_foreign_service_account(self):
        provider = S3.__new__(S3)
        provider.admin = Mock(return_value={'parentUser': 'a-different-managed-parent'})
        with self.assertRaises(StoreError):
            provider.revoke({'resource_id': str(uuid4())}, {'credential_id': str(uuid4())})
        self.assertEqual(provider.admin.call_count, 1)
        self.assertEqual(provider.admin.call_args.args[:2], ('GET', 'info-service-account'))
