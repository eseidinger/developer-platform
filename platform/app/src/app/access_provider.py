"""Keycloak projection for platform-owned groups, browser clients and service identities."""
import base64
import hashlib
import hmac
import os
from urllib.parse import quote, urlencode

from .keycloak_credentials import ProviderError, _admin_token, _request


def derived_secret(identifier, purpose):
    return base64.urlsafe_b64encode(hmac.new(os.environ["DATABASE_KEY"].encode(),
        ("hosted-access:" + purpose + ":" + identifier).encode(), hashlib.sha256).digest()).decode()


def audience(application_id):
    return "app-" + application_id


class KeycloakAccessProvider:
    """Idempotent outward-only projection; never imports provider permissions."""

    def __init__(self):
        self.token = None

    def call(self, path, method="GET", body=None, missing=False):
        if self.token is None:
            self.token = _admin_token()
        return _request("/admin/realms/platform/" + path, method=method, body=body,
                        token=self.token, allow_not_found=missing)[1]

    def find_client(self, client_id):
        rows = self.call("clients?" + urlencode({"clientId": client_id})) or []
        if len(rows) > 1:
            raise ProviderError("Ambiguous hosted identity")
        return rows[0] if rows else None

    def client(self, representation):
        found = self.find_client(representation["clientId"])
        if found:
            self.call("clients/" + found["id"], "PUT", representation)
        else:
            self.call("clients", "POST", representation)
            found = self.find_client(representation["clientId"])
        if not found:
            raise ProviderError("Hosted client could not be resolved")
        return found["id"]

    def group_mapper(self, resource_client):
        return {"name": "platform application groups", "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-client-role-mapper", "consentRequired": False,
            "config": {"usermodel.clientRoleMapping.clientId": resource_client,
                "usermodel.clientRoleMapping.rolePrefix": "", "claim.name": "groups",
                "jsonType.label": "String", "multivalued": "true", "id.token.claim": "true",
                "access.token.claim": "true", "userinfo.token.claim": "true"}}

    def mappers(self, resource_client):
        return [self.group_mapper(resource_client), {"name": "platform target audience",
            "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
            "consentRequired": False, "config": {"included.client.audience": resource_client,
                "access.token.claim": "true", "id.token.claim": "false"}}]

    def resource(self, application_id):
        return self.client({"clientId": audience(application_id), "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "bearerOnly": True,
            "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
            "fullScopeAllowed": False, "defaultClientScopes": [], "optionalClientScopes": []})

    def role(self, application_id, group_id):
        cid = self.resource(application_id)
        path = "clients/" + cid + "/roles/" + quote(group_id, safe="")
        role = self.call(path, missing=True)
        if not role:
            self.call("clients/" + cid + "/roles", "POST", {"name": group_id})
            role = self.call(path)
        return cid, role

    def browser(self, policy, host, groups):
        app_id = policy["spec"]["applicationId"]
        resource_id = self.resource(app_id)
        client_id = "browser-" + policy["id"]
        cid = self.client({"clientId": client_id, "enabled": True, "protocol": "openid-connect",
            "publicClient": False, "secret": derived_secret(policy["id"], "browser"),
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False, "fullScopeAllowed": False,
            "redirectUris": ["https://" + host + "/oauth2/callback"], "webOrigins": ["https://" + host],
            "defaultClientScopes": ["basic", "profile", "email"], "optionalClientScopes": [],
            "attributes": {"pkce.code.challenge.method": "S256", "access.token.lifespan": "300",
                "client.session.idle.timeout": "1800", "client.session.max.lifespan": "28800"},
            "protocolMappers": self.mappers(audience(app_id))})
        roles = [self.role(app_id, gid)[1] for gid in groups]
        self.call("clients/" + cid + "/scope-mappings/clients/" + resource_id, "POST", roles)
        return client_id

    def service(self, policy, credential_id, groups):
        app_id = policy["spec"]["applicationId"]
        resource_id = self.resource(app_id)
        client_id = "service-" + credential_id
        secret = derived_secret(credential_id, "machine")
        cid = self.client({"clientId": client_id, "enabled": True, "protocol": "openid-connect",
            "publicClient": False, "secret": secret, "serviceAccountsEnabled": True,
            "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
            "fullScopeAllowed": False, "defaultClientScopes": [], "optionalClientScopes": [],
            "attributes": {"access.token.lifespan": "300"}, "protocolMappers": self.mappers(audience(app_id))})
        user = self.call("clients/" + cid + "/service-account-user")
        if not user or not user.get("id"):
            raise ProviderError("Missing service principal")
        roles = [self.role(app_id, gid)[1] for gid in groups]
        self.call("clients/" + cid + "/scope-mappings/clients/" + resource_id, "POST", roles)
        self.set_membership(app_id, user["id"], groups)
        return {"clientId": client_id, "subject": user["id"], "secret": secret}

    def set_membership(self, application_id, subject, group_ids):
        if self.call("users/" + quote(subject, safe=""), missing=True) is None:
            if not group_ids:
                return  # A deleted realm account has already lost every application role.
            raise ProviderError("Application identity no longer exists")
        cid = self.resource(application_id)
        path = "users/" + quote(subject, safe="") + "/role-mappings/clients/" + cid
        current = self.call(path) or []
        wanted = [self.role(application_id, gid)[1] for gid in group_ids]
        remove = [r for r in current if r["name"] not in group_ids]
        if remove:
            self.call(path, "DELETE", remove)
        if wanted:
            self.call(path, "POST", wanted)

    def delete_client(self, client_id):
        found = self.find_client(client_id)
        if found:
            self.call("clients/" + found["id"], "DELETE", missing=True)

    def delete_role(self, application_id, group_id):
        found = self.find_client(audience(application_id))
        if found:
            self.call("clients/" + found["id"] + "/roles/" + quote(group_id, safe=""), "DELETE", missing=True)
