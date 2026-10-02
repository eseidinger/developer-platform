import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from app import main


class PortalTests(unittest.TestCase):
    def test_portal_serves_the_pkce_ui(self):
        response = main.portal()
        self.assertTrue(response.path.endswith("app/static/portal.html"))
        self.assertTrue(Path(response.path).is_file())

    def test_portal_config_has_only_public_oidc_settings(self):
        request = Mock()
        request.base_url = "https://platform.example.com/"
        request.url.hostname = "platform.example.com"
        with patch.dict(os.environ, {"OIDC_ISSUER": "https://identity.example.com/realms/platform",
                                     "PLATFORM_DOMAIN": "platform.example.com"}):
            config = main.portal_config(request)
        self.assertEqual(config, {
            "issuer": "https://identity.example.com/realms/platform",
            "client_id": "platform-portal",
            "redirect_uri": "https://platform.example.com/",
        })

    def test_portal_config_uses_local_request_uri_for_local_development(self):
        request = Mock()
        request.base_url = "http://localhost:8000/"
        request.url.hostname = "localhost"
        self.assertEqual(main.portal_config(request)["redirect_uri"], "http://localhost:8000/")
