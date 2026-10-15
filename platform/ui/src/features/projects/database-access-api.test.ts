import { describe, expect, it, vi } from 'vitest'

import { parseCredential, parseGrant, parseGrants, parseMyAccess, revokeHumanDatabaseGrant } from './database-access-api'

const requests = vi.hoisted(() => ({ DELETE: vi.fn() }))
vi.mock('@/api/client', () => ({ apiClient: requests }))

const grant = {
  project: 'demo', issuer: 'https://identity.example', subject: 'person-1',
  username: 'human_abc', key_fingerprint: 'SHA256:abc', active: true,
  created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z',
  public_key: 'must-not-be-rendered', password: 'must-not-be-rendered',
}

describe('human database access response boundaries', () => {
  it('sends only the required issuer and subject when revoking a grant', async () => {
    requests.DELETE.mockResolvedValueOnce({ error: undefined, response: new Response(null, { status: 200 }) })
    await revokeHumanDatabaseGrant('demo', parseGrant(grant))
    expect(requests.DELETE).toHaveBeenCalledWith('/projects/{name}/database-access/grants', {
      params: { path: { name: 'demo' } },
      body: { issuer: grant.issuer, subject: grant.subject },
    })
  })

  it('keeps only safe grant metadata and rejects malformed lists', () => {
    expect(parseGrant(grant)).toEqual({
      project: 'demo', issuer: 'https://identity.example', subject: 'person-1',
      username: 'human_abc', keyFingerprint: 'SHA256:abc', active: true,
      createdAt: '2026-10-14T10:00:00Z', updatedAt: '2026-10-14T10:00:00Z',
    })
    expect(parseGrants({ project: 'demo', grants: [grant] })).toHaveLength(1)
    expect(() => parseGrants({ grants: [{ ...grant, active: 'yes' }] })).toThrow('invalid human database access')
  })

  it('validates the personal connection details and one-time response', () => {
    expect(parseMyAccess({ ...grant, database: 'project_demo', ssh_user: 'platform-db' }).database).toBe('project_demo')
    expect(() => parseMyAccess({ ...grant, database: 1, ssh_user: 'platform-db' })).toThrow('invalid personal database')
    expect(parseCredential({ project: 'demo', database: 'project_demo', username: 'human_abc', password: 'once' }).password).toBe('once')
    expect(() => parseCredential({ project: 'demo', database: 'project_demo', username: 'human_abc' })).toThrow('invalid one-time')
  })
})
