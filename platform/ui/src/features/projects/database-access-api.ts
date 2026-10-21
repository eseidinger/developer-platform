import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'

type HumanDatabaseGrant = {
  project: string
  issuer: string
  subject: string
  username: string
  keyFingerprint: string
  active: boolean
  createdAt: string
  updatedAt: string
}

type MyDatabaseAccess = HumanDatabaseGrant & {
  database: string
  sshUser: string
}
type OneTimeDatabaseCredential = {
  project: string
  database: string
  username: string
  password: string
}
type NewHumanDatabaseGrant = {
  issuer: string
  subject: string
  publicKey: string
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function parseGrant(value: unknown): HumanDatabaseGrant {
  const item = record(value)
  if (
    !item ||
    typeof item.project !== 'string' ||
    typeof item.issuer !== 'string' ||
    typeof item.subject !== 'string' ||
    typeof item.username !== 'string' ||
    typeof item.key_fingerprint !== 'string' ||
    typeof item.active !== 'boolean' ||
    typeof item.created_at !== 'string' ||
    typeof item.updated_at !== 'string'
  ) {
    throw new Error(
      'The platform returned invalid human database access metadata.',
    )
  }
  return {
    project: item.project,
    issuer: item.issuer,
    subject: item.subject,
    username: item.username,
    keyFingerprint: item.key_fingerprint,
    active: item.active,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  }
}

function parseGrants(value: unknown): HumanDatabaseGrant[] {
  const body = record(value)
  if (!body || !Array.isArray(body.grants)) {
    throw new Error(
      'The platform returned an invalid human database grant list.',
    )
  }
  return body.grants.map(parseGrant)
}

function parseMyAccess(value: unknown): MyDatabaseAccess {
  const body = record(value)
  if (
    !body ||
    typeof body.database !== 'string' ||
    typeof body.ssh_user !== 'string'
  ) {
    throw new Error(
      'The platform returned invalid personal database access metadata.',
    )
  }
  return {
    ...parseGrant(body),
    database: body.database,
    sshUser: body.ssh_user,
  }
}

function parseCredential(value: unknown): OneTimeDatabaseCredential {
  const body = record(value)
  if (
    !body ||
    typeof body.project !== 'string' ||
    typeof body.database !== 'string' ||
    typeof body.username !== 'string' ||
    typeof body.password !== 'string' ||
    !body.password
  ) {
    throw new Error(
      'The platform returned an invalid one-time database credential.',
    )
  }
  return {
    project: body.project,
    database: body.database,
    username: body.username,
    password: body.password,
  }
}

async function listHumanDatabaseGrants(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/projects/{name}/database-access/grants',
    { params: { path: { name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  return parseGrants(data)
}

async function createHumanDatabaseGrant(
  name: string,
  grant: NewHumanDatabaseGrant,
) {
  const { data, error, response } = await apiClient.POST(
    '/projects/{name}/database-access/grants',
    {
      params: { path: { name } },
      body: {
        issuer: grant.issuer,
        subject: grant.subject,
        public_key: grant.publicKey,
      },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  return parseGrant(data)
}

async function revokeHumanDatabaseGrant(
  name: string,
  grant: Pick<HumanDatabaseGrant, 'issuer' | 'subject'>,
) {
  const { error, response } = await apiClient.DELETE(
    '/projects/{name}/database-access/grants',
    {
      params: { path: { name } },
      body: { issuer: grant.issuer, subject: grant.subject },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function getMyDatabaseAccess(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/projects/{name}/database-access/me',
    { params: { path: { name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  return parseMyAccess(data)
}

async function replaceMyDatabaseKey(name: string, publicKey: string) {
  const { data, error, response } = await apiClient.PUT(
    '/projects/{name}/database-access/me/key',
    {
      params: { path: { name } },
      body: { public_key: publicKey },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  return parseGrant(data)
}

async function issueMyDatabaseCredential(name: string) {
  const { data, error, response } = await apiClient.POST(
    '/projects/{name}/database-access/me/credential',
    {
      params: { path: { name } },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  return parseCredential(data)
}

export {
  createHumanDatabaseGrant,
  getMyDatabaseAccess,
  issueMyDatabaseCredential,
  listHumanDatabaseGrants,
  replaceMyDatabaseKey,
  revokeHumanDatabaseGrant,
}
export { parseCredential, parseGrant, parseGrants, parseMyAccess }
export type {
  HumanDatabaseGrant,
  MyDatabaseAccess,
  NewHumanDatabaseGrant,
  OneTimeDatabaseCredential,
}
