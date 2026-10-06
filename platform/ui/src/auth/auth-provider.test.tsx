import { describe, expect, it } from 'vitest'

import { parsePortalAuthConfig } from '@/auth/config'

describe('parsePortalAuthConfig', () => {
  it('maps the public portal configuration to the client shape', () => {
    expect(
      parsePortalAuthConfig({
        issuer: 'https://identity.example.com/realms/platform',
        client_id: 'platform-portal',
        redirect_uri: 'https://platform.example.com/',
      }),
    ).toEqual({
      issuer: 'https://identity.example.com/realms/platform',
      clientId: 'platform-portal',
      redirectUri: 'https://platform.example.com/',
    })
  })

  it('rejects missing or malformed public configuration', () => {
    expect(() => parsePortalAuthConfig({ client_id: 'platform-portal' })).toThrow(
      'invalid public OIDC configuration',
    )
  })
})
