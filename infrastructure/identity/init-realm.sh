#!/bin/sh
set -e

kcadm() {
  /opt/keycloak/bin/kcadm.sh "$@"
}

# Preserve the CLI's existing ID extraction for each client type.
client_id() {
  kcadm get clients -r platform -q "clientId=$1" --fields id \
    | sed -n 's/.*"id" *: *"\([^"]*\)".*/\1/p'
}

console_client_id() {
  kcadm get clients -r platform -q clientId=platform-store-console --fields id \
    | sed -n 's/.*"id" *: *"\([^" ]*\)".*/\1/p'
}

# Realm import must finish before administrator authentication can succeed.
until kcadm config credentials --server http://keycloak:8080 --realm master \
  --user admin --password "$KEYCLOAK_ADMIN_PASSWORD"; do
  sleep 2
done

# Public portal: allow the hosted UI and the supported local development URLs.
portal_id=$(client_id platform-portal)
if [ -z "$portal_id" ]; then
  kcadm create clients -r platform \
    -s clientId=platform-portal -s name='Developer Platform Portal' \
    -s enabled=true -s protocol=openid-connect -s publicClient=true \
    -s standardFlowEnabled=true -s directAccessGrantsEnabled=false
  portal_id=$(client_id platform-portal)
fi
test -n "$portal_id"

redirect_uris=$(cat <<EOF
["https://$PLATFORM_DOMAIN/*", "http://localhost/*", "http://localhost:8000/*",
 "http://127.0.0.1:8000/*", "https://platform.localhost/*"]
EOF
)
web_origins=$(cat <<EOF
["https://$PLATFORM_DOMAIN", "http://localhost", "http://localhost:5173",
 "http://localhost:8000", "http://127.0.0.1:8000", "https://platform.localhost"]
EOF
)
audience_mapper=$(cat <<'JSON'
[{
  "name": "platform-api audience",
  "protocol": "openid-connect",
  "protocolMapper": "oidc-audience-mapper",
  "consentRequired": false,
  "config": {
    "included.client.audience": "platform-api",
    "id.token.claim": "false",
    "access.token.claim": "true"
  }
}]
JSON
)

kcadm update "clients/$portal_id" -r platform \
  -s "redirectUris=$redirect_uris" \
  -s "webOrigins=$web_origins" \
  -s 'attributes={"pkce.code.challenge.method":"S256"}' \
  -s "protocolMappers=$audience_mapper"

# Confidential console: keep the secret synchronized and require PKCE.
console_id=$(console_client_id)
if [ -z "$console_id" ]; then
  kcadm create clients -r platform \
    -s clientId=platform-store-console -s name='Platform Store Console' \
    -s enabled=true -s protocol=openid-connect -s publicClient=false \
    -s standardFlowEnabled=true -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=false
  console_id=$(console_client_id)
fi
test -n "$console_id"

kcadm update "clients/$console_id" -r platform \
  -s enabled=true -s publicClient=false -s standardFlowEnabled=true \
  -s directAccessGrantsEnabled=false -s serviceAccountsEnabled=false \
  -s "secret=$STORE_CONSOLE_OIDC_SECRET" \
  -s "redirectUris=[\"https://$PLATFORM_DOMAIN/store-console/postgresql/\
oauth2/authorize\"]" \
  -s 'attributes={"pkce.code.challenge.method":"S256"}'

# Provisioning service account: no interactive login; retain its existing grants.
provisioner_id=$(client_id platform-credential-provisioner)
if [ -z "$provisioner_id" ]; then
  kcadm create clients -r platform \
    -s clientId=platform-credential-provisioner \
    -s name='Platform Credential Provisioner' \
    -s enabled=true -s protocol=openid-connect -s publicClient=false \
    -s serviceAccountsEnabled=true -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false -s "secret=$KEYCLOAK_PROVISIONER_SECRET"
  provisioner_id=$(client_id platform-credential-provisioner)
else
  kcadm update "clients/$provisioner_id" -r platform \
    -s enabled=true -s serviceAccountsEnabled=true \
    -s "secret=$KEYCLOAK_PROVISIONER_SECRET"
fi

service_user_id=$(kcadm get "clients/$provisioner_id/service-account-user" \
  -r platform --fields id | sed -n 's/.*"id" *: *"\([^"]*\)".*/\1/p')
kcadm add-roles -r platform --uid "$service_user_id" \
  --cclientid realm-management --rolename manage-clients \
  --rolename manage-users --rolename view-users
