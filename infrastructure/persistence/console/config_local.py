"""Pinned pgAdmin server policy. Only the edge proxy and lease relay are reachable."""

import os
from pathlib import Path

# Public issuers use the image's system roots. For local development, bootstrap
# exports only Caddy's public CA into this read-only mount; no CA keys are shared.
identity_domain = os.environ["IDENTITY_DOMAIN"].lower().rstrip(".")
local_identity = identity_domain == "localhost" or identity_domain.endswith(
    ".localhost"
)
identity_verification = "/run/platform-trust/local-ca.pem" if local_identity else True
if local_identity and not Path(identity_verification).is_file():
    raise RuntimeError("Run scripts/setup/prepare-local-trust.py before local pgAdmin")

AUTHENTICATION_SOURCES = ["oauth2"]
OAUTH2_AUTO_CREATE_USER = True
OAUTH2_CONFIG = [
    {
        "OAUTH2_NAME": "platform",
        "OAUTH2_DISPLAY_NAME": "Platform sign-in",
        "OAUTH2_CLIENT_ID": "platform-store-console",
        "OAUTH2_CLIENT_SECRET": os.environ["STORE_CONSOLE_OIDC_SECRET"],
        "OAUTH2_SERVER_METADATA_URL": "https://"
        + os.environ["IDENTITY_DOMAIN"]
        + "/realms/platform/.well-known/openid-configuration",
        "OAUTH2_SCOPE": "openid email profile",
        # Never merge users because a mutable email/username is reused.
        "OAUTH2_USERNAME_CLAIM": "sub",
        "OAUTH2_CHALLENGE_METHOD": "S256",
        "OAUTH2_RESPONSE_TYPE": "code",
        "OAUTH2_SSL_CERT_VERIFICATION": identity_verification,
    }
]
# No durable data passwords or shared administrator server registrations.
MASTER_PASSWORD_REQUIRED = False
ALLOW_SAVE_PASSWORD = False
ENABLE_PSQL = False
ENABLE_BINARY_PATH_BROWSING = False
UPGRADE_CHECK_ENABLED = False
CHECK_SUPPORTED_BROWSER = False
SESSION_COOKIE_NAME = "platform_store_console"
SESSION_COOKIE_PATH = "/store-console/postgresql/"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
PROXY_X_PROTO_COUNT = 1
PROXY_X_HOST_COUNT = 1
PROXY_X_PREFIX_COUNT = 1
CONSOLE_LOG_LEVEL = 30
FILE_LOG_LEVEL = 50
# Keep reviewed, bounded per-user/database SQL history. Zero in this release
# retains the first entry and is not a disable switch. No query results are sent
# into platform telemetry by this integration.
MAX_QUERY_HIST_STORED = 20
