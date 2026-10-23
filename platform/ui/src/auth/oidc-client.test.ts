import { describe, expect, it } from 'vitest'
import { createUserManager } from '@/auth/oidc-client'

describe('portal OIDC client', () => {
  it('enables automatic renewal and redirects logout back to the portal', () => {
    const manager = createUserManager({
      issuer: 'https://identity.example/realms/platform',
      clientId: 'platform-portal',
      redirectUri: 'https://platform.example/',
    })
    expect(manager.settings.automaticSilentRenew).toBe(true)
    expect(manager.settings.post_logout_redirect_uri).toBe(
      'https://platform.example/',
    )
    expect(manager.settings.response_type).toBe('code')
    manager.stopSilentRenew()
  })
})
