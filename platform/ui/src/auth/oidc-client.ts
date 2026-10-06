import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from 'oidc-client-ts'

import type { PortalAuthConfig } from '@/auth/config'

function createUserManager(config: PortalAuthConfig) {
  return new UserManager({
    authority: config.issuer,
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    post_logout_redirect_uri: config.redirectUri,
    response_type: 'code',
    scope: 'openid profile email',
    automaticSilentRenew: false,
    monitorSession: false,
    loadUserInfo: false,
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
  })
}

export { createUserManager }
