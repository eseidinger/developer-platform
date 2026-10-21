import { z } from 'zod'

import { apiClient } from '@/api/client'
import { ApiError, apiErrorFromResponse } from '@/api/errors'
import type { components } from '@/api/generated/schema'

export type PolicyInput = components['schemas']['PolicyCreate']
export type GovernanceInput = components['schemas']['Governance']
export type ServiceInput = components['schemas']['ServiceRequest']
export type GroupInput = components['schemas']['GroupCreate']
export type RouteInput = components['schemas']['Route']

const methods = z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
export const routeSchema = z.object({
  name: z.string().min(1).max(64),
  match: z.object({
    path: z.string().nullable().optional(),
    pathPrefix: z.string().nullable().optional(),
    methods: z.array(methods).min(1),
  }),
  authentication: z.object({
    mode: z.enum(['browser-session', 'bearer-token']),
  }),
  authorization: z.object({ anyOfGroups: z.array(z.string()).min(1).max(50) }),
})
export const governanceSchema = z.object({
  maximumDataClassification: z.enum(['Public', 'Internal', 'Confidential']),
  maximumTelemetryClassification: z.enum([
    'Public',
    'Internal',
    'Confidential',
  ]),
  personalData: z.boolean(),
  domainRetentionOwner: z.string().min(1).max(200),
  domainRetentionPolicy: z.string().min(1).max(2000),
  purgeAuthority: z.string().min(1).max(200),
  recoveryOwner: z.string().min(1).max(200),
})
const policySchema = z.object({
  component: z.string(),
  defaultDecision: z.literal('deny'),
  identityAttributes: z.object({
    displayName: z.boolean(),
    email: z.boolean(),
  }),
  routes: z.array(routeSchema).min(1).max(100),
  host: z.string(),
  revisionId: z.string().optional(),
  previousRevision: z.string().nullable().optional(),
})
const groupSchema = z.object({ displayName: z.string() })
const humanSchema = z.object({
  policyId: z.string(),
  principalId: z.string(),
  issuer: z.string(),
  subject: z.string(),
  expiresAt: z.string(),
})
const membershipSchema = humanSchema
  .omit({ expiresAt: true })
  .extend({ groupId: z.string() })
const credentialSchema = z.object({
  id: z.string(),
  state: z.string(),
  expiresAt: z.string().optional(),
})
const serviceSchema = z.object({
  providerProject: z.string(),
  application: z.string(),
  projectWideCredential: z.literal(true),
  policyId: z.string(),
  principalId: z.string(),
  groups: z.array(z.string()),
  credentials: z.array(credentialSchema),
  secretPrefix: z
    .string()
    .regex(/^ACCESS_[A-Z0-9]+$/)
    .optional(),
  audience: z.string().optional(),
  providerUrl: z
    .url()
    .refine(
      (value) => new URL(value).protocol === 'https:',
      'Expected an HTTPS provider URL',
    )
    .optional(),
  adoption: z.string().optional(),
})
const envelope = z.object({
  id: z.string(),
  project: z.string(),
  name: z.string(),
  state: z.string(),
  version: z.number().int().positive(),
  created_at: z.string(),
  updated_at: z.string(),
  operation_id: z.string().optional(),
})
const resourceSchemas = {
  group: envelope.extend({ kind: z.literal('group'), spec: groupSchema }),
  policy: envelope.extend({ kind: z.literal('policy'), spec: policySchema }),
  'policy-revision': envelope.extend({
    kind: z.literal('policy-revision'),
    spec: policySchema.omit({ revisionId: true }),
  }),
  governance: envelope.extend({
    kind: z.literal('governance'),
    spec: governanceSchema,
  }),
  'human-request': envelope.extend({
    kind: z.literal('human-request'),
    spec: humanSchema,
  }),
  membership: envelope.extend({
    kind: z.literal('membership'),
    spec: membershipSchema,
  }),
  'service-access': envelope.extend({
    kind: z.literal('service-access'),
    spec: serviceSchema,
  }),
}
export type Group = z.infer<typeof resourceSchemas.group>
export type Policy = z.infer<typeof resourceSchemas.policy>
export type Governance = z.infer<typeof resourceSchemas.governance>
export type HumanRequest = z.infer<(typeof resourceSchemas)['human-request']>
export type Membership = z.infer<typeof resourceSchemas.membership>
export type ServiceAccess = z.infer<(typeof resourceSchemas)['service-access']>
export type Resource =
  Group | Policy | Governance | HumanRequest | Membership | ServiceAccess
type Kind = keyof typeof resourceSchemas

const contextSchema = z.object({
  project: z.string(),
  application: z.string(),
  status: z.string(),
  eligible: z.boolean(),
  reason: z.string().nullable(),
  component: z.string().nullable(),
  url: z
    .url()
    .refine((value) => new URL(value).protocol === 'https:')
    .nullable(),
  permissions: z.object({ manage: z.boolean(), consume: z.boolean() }),
})
export type AccessContext = z.infer<typeof contextSchema>
const operationSchema = z.object({
  id: z.string(),
  resourceId: z.string(),
  resourceVersion: z.number().int().positive(),
  action: z.string(),
  state: z.enum(['queued', 'running', 'succeeded', 'failed']),
  attempts: z.number().int(),
  errorCode: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
  canRetry: z.boolean(),
})
export type AccessOperation = z.infer<typeof operationSchema>

export const accessKeys = {
  project: (project: string) => ['application-access', project] as const,
  resource: (project: string, kind: string) =>
    [...accessKeys.project(project), kind] as const,
}

type Result = { data?: unknown; error?: unknown; response: Response }
function checked(result: Result) {
  if (!result.response.ok) {
    if (result.response.status === 422)
      throw new ApiError(
        'The access settings were rejected. Check the fields and supported policy rules.',
        422,
      )
    throw apiErrorFromResponse(result.response, result.error)
  }
  return result.data
}
function parse<T>(schema: z.ZodType<T>, value: unknown): T {
  const parsed = schema.safeParse(value)
  if (!parsed.success)
    throw new Error(
      'The platform returned an invalid application-access response.',
    )
  return parsed.data
}
export function parseAccessResource(kind: Kind, value: unknown) {
  return parse<z.infer<(typeof resourceSchemas)[Kind]>>(
    resourceSchemas[kind],
    value,
  )
}
function list<T>(schema: z.ZodType<T>, result: Result): T[] {
  return parse(z.object({ items: z.array(schema) }), checked(result)).items
}
function optional<T>(
  schema: z.ZodType<T>,
  result: Result,
  missing: string,
): T | null {
  if (
    result.response.status === 404 &&
    apiErrorFromResponse(result.response, result.error).message === missing
  )
    return null
  return parse(schema, checked(result))
}
const path = (project: string) => ({ project })
const policyPath = (project: string) => ({ project, application: project })
const resourcePath = (project: string, id: string) => ({
  project,
  resource_id: id,
})
export const etag = (version: number) => `"${version}"`

export async function getAccessContext(project: string, signal?: AbortSignal) {
  return parse(
    contextSchema,
    checked(
      await apiClient.GET('/v1/projects/{project}/application-access-context', {
        params: { path: path(project) },
        signal,
      }),
    ),
  )
}
export async function getAccessCapabilities(signal?: AbortSignal) {
  const result = checked(await apiClient.GET('/v1/capabilities', { signal }))
  return (
    parse(
      z.object({
        hostedApplicationAccess: z
          .object({
            modes: z.array(z.enum(['browser-session', 'bearer-token'])),
            requires: z.string(),
            authorization: z.string(),
            maxAuthorizationStalenessSeconds: z.number(),
            credentialIsolation: z.string(),
          })
          .optional(),
      }),
      result,
    ).hostedApplicationAccess ?? null
  )
}
export async function getAccessReadiness(
  project: string,
  signal?: AbortSignal,
) {
  return parse(
    z.object({
      components: z.array(
        z.object({
          name: z.string(),
          status: z
            .object({
              state: z.string(),
              reason: z.string().nullable().optional(),
            })
            .optional(),
        }),
      ),
    }),
    checked(
      await apiClient.GET('/projects/{name}/components', {
        params: { path: { name: project } },
        signal,
      }),
    ),
  )
}
export async function getGroups(project: string, signal?: AbortSignal) {
  return list(
    resourceSchemas.group,
    await apiClient.GET('/v1/projects/{project}/application-groups', {
      params: { path: path(project) },
      signal,
    }),
  )
}
export async function getPolicy(project: string, signal?: AbortSignal) {
  return optional(
    resourceSchemas.policy,
    await apiClient.GET(
      '/v1/projects/{project}/applications/{application}/access-policy',
      { params: { path: policyPath(project) }, signal },
    ),
    'Access policy is not configured',
  )
}
export async function getGovernance(project: string, signal?: AbortSignal) {
  return optional(
    resourceSchemas.governance,
    await apiClient.GET('/v1/projects/{project}/governance', {
      params: { path: path(project) },
      signal,
    }),
    'Project governance is not recorded',
  )
}
export async function getPolicyRevisions(
  project: string,
  signal?: AbortSignal,
) {
  return list(
    resourceSchemas['policy-revision'],
    await apiClient.GET(
      '/v1/projects/{project}/applications/{application}/access-policy/revisions',
      { params: { path: policyPath(project) }, signal },
    ),
  )
}
export async function getHumanRequests(project: string, signal?: AbortSignal) {
  return list(
    resourceSchemas['human-request'],
    await apiClient.GET('/v1/projects/{project}/application-access-requests', {
      params: { path: path(project) },
      signal,
    }),
  )
}
export async function getMemberships(project: string, signal?: AbortSignal) {
  return list(
    resourceSchemas.membership,
    await apiClient.GET(
      '/v1/projects/{project}/application-group-memberships',
      { params: { path: path(project) }, signal },
    ),
  )
}
export async function getServices(project: string, signal?: AbortSignal) {
  return list(
    resourceSchemas['service-access'],
    await apiClient.GET('/v1/projects/{project}/service-access-requests', {
      params: { path: path(project) },
      signal,
    }),
  )
}
export async function getAccessOperations(
  project: string,
  signal?: AbortSignal,
) {
  return list(
    operationSchema,
    await apiClient.GET(
      '/v1/projects/{project}/application-access-operations',
      { params: { path: path(project) }, signal },
    ),
  )
}
export async function createGroup(
  project: string,
  body: GroupInput,
  key: string,
) {
  return parse(
    resourceSchemas.group,
    checked(
      await apiClient.POST('/v1/projects/{project}/application-groups', {
        params: { path: path(project), header: { 'Idempotency-Key': key } },
        body,
      }),
    ),
  )
}
export async function deleteGroup(
  project: string,
  id: string,
  version: number,
) {
  return parse(
    resourceSchemas.group,
    checked(
      await apiClient.DELETE(
        '/v1/projects/{project}/application-groups/{resource_id}',
        {
          params: {
            path: resourcePath(project, id),
            header: { 'If-Match': etag(version) },
          },
        },
      ),
    ),
  )
}
export async function saveGovernance(
  project: string,
  body: GovernanceInput,
  version?: number,
) {
  return parse(
    resourceSchemas.governance,
    checked(
      await apiClient.PUT('/v1/projects/{project}/governance', {
        params: {
          path: path(project),
          header: {
            'If-Match': version === undefined ? undefined : etag(version),
          },
        },
        body,
      }),
    ),
  )
}
export async function savePolicy(
  project: string,
  body: PolicyInput,
  version?: number,
) {
  return parse(
    resourceSchemas.policy,
    checked(
      await apiClient.PUT(
        '/v1/projects/{project}/applications/{application}/access-policy',
        {
          params: {
            path: policyPath(project),
            header: { 'If-Match': etag(version ?? 0) },
          },
          body,
        },
      ),
    ),
  )
}
export async function rollbackPolicy(project: string, version: number) {
  return parse(
    resourceSchemas.policy,
    checked(
      await apiClient.POST(
        '/v1/projects/{project}/applications/{application}/access-policy/rollback',
        {
          params: {
            path: policyPath(project),
            header: { 'If-Match': etag(version) },
          },
        },
      ),
    ),
  )
}
export type HumanAction = 'approve' | 'reject' | 'cancel' | 'reopen' | 'groups'
export async function changeHuman(
  project: string,
  id: string,
  version: number,
  action: HumanAction,
  groups: string[] = [],
) {
  const params = {
    path: resourcePath(project, id),
    header: { 'If-Match': etag(version) },
  }
  const calls = {
    approve: () =>
      apiClient.POST(
        '/v1/projects/{project}/application-access-requests/{resource_id}/approve',
        { params, body: { groups } },
      ),
    groups: () =>
      apiClient.POST(
        '/v1/projects/{project}/application-access-requests/{resource_id}/groups',
        { params, body: { groups } },
      ),
    reject: () =>
      apiClient.POST(
        '/v1/projects/{project}/application-access-requests/{resource_id}/reject',
        { params },
      ),
    cancel: () =>
      apiClient.POST(
        '/v1/projects/{project}/application-access-requests/{resource_id}/cancel',
        { params },
      ),
    reopen: () =>
      apiClient.POST(
        '/v1/projects/{project}/application-access-requests/{resource_id}/reopen',
        { params },
      ),
  }
  return parse(resourceSchemas['human-request'], checked(await calls[action]()))
}
export async function revokeMembership(
  project: string,
  id: string,
  version: number,
) {
  return parse(
    resourceSchemas.membership,
    checked(
      await apiClient.DELETE(
        '/v1/projects/{project}/application-group-memberships/{resource_id}',
        {
          params: {
            path: resourcePath(project, id),
            header: { 'If-Match': etag(version) },
          },
        },
      ),
    ),
  )
}
export async function requestService(
  project: string,
  body: ServiceInput,
  key: string,
) {
  return parse(
    resourceSchemas['service-access'],
    checked(
      await apiClient.POST('/v1/projects/{project}/service-access-requests', {
        params: { path: path(project), header: { 'Idempotency-Key': key } },
        body,
      }),
    ),
  )
}
export type ServiceAction =
  | 'approve'
  | 'reject'
  | 'cancel'
  | 'rotate'
  | 'emergency'
  | 'confirm'
  | 'revoke'
export async function changeService(
  project: string,
  id: string,
  version: number,
  action: ServiceAction,
  groups: string[] = [],
) {
  const params = {
    path: resourcePath(project, id),
    header: { 'If-Match': etag(version) },
  }
  const calls = {
    approve: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/approve',
        { params, body: { groups } },
      ),
    reject: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/reject',
        { params },
      ),
    cancel: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/cancel',
        { params },
      ),
    rotate: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/rotate',
        { params, body: { emergency: false } },
      ),
    emergency: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/rotate',
        { params, body: { emergency: true } },
      ),
    confirm: () =>
      apiClient.POST(
        '/v1/projects/{project}/service-access-requests/{resource_id}/confirm',
        { params },
      ),
    revoke: () =>
      apiClient.DELETE(
        '/v1/projects/{project}/service-access-requests/{resource_id}',
        { params },
      ),
  }
  return parse(
    resourceSchemas['service-access'],
    checked(await calls[action]()),
  )
}
export async function retryAccessOperation(
  operationId: string,
  version: number,
) {
  const data = checked(
    await apiClient.POST('/v1/access-operations/{operation_id}/retry', {
      params: {
        path: { operation_id: operationId },
        header: { 'If-Match': etag(version) },
      },
    }),
  )
  const kind = parse(
    z.object({
      kind: z.enum([
        'group',
        'policy',
        'governance',
        'human-request',
        'membership',
        'service-access',
      ]),
    }),
    data,
  ).kind
  return parseAccessResource(kind, data)
}

// Store only the last submitted intent in component memory, never credentials.
export class IdempotentIntent {
  private signature: string | undefined
  private key = ''
  keyFor(body: GroupInput | ServiceInput) {
    const signature = JSON.stringify(body)
    if (signature !== this.signature) {
      this.signature = signature
      this.key = crypto.randomUUID()
    }
    return this.key
  }
}

export function requireVersion(version: number | undefined) {
  if (version === undefined)
    throw new Error('Reload the current resource before submitting.')
  return version
}
