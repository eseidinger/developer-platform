import { describe, expect, it } from 'vitest'

import { parseCredential, parseGrant, parseGrants, parseMyAccess } from './database-access-api'

const grant = {
  project: 'demo', issuer: 'https://identity.example', subject: 'person-1',
  username: 'human_abc', key_fingerprint: 'SHA256:abc', active: true,
  created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z',
  public_key: 'must-not-be-rendered', password: 'must-not-be-rendered',
}

describe('human database access response boundaries', () => {
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
