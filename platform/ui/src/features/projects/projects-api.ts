import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'

type ProjectSummary = {
  name: string
  status: string
}

type EmptyProjectCreate = {
  name: string
}

type ProjectRevision = {
  revision: number
  createdAt: string
  current: boolean
  image: string | null
}

type ProjectRevisions = {
  project: string
  currentRevision: number | null
  revisions: ProjectRevision[]
}

type ProjectDeployment = {
  name: string
  image: string
  port: number
  probe_profile: 'status' | 'hello-world'
}

type OperationAccepted = {
  operationId: string
  state: string
  revision: number
}
type OperationStatus = {
  state: string
  revision: number
  errorCode: string | null
  readinessState: string
  readinessReason: string | null
}
type ResourceUsagePod = {
  name: string
  cpuMillicores: number
  memoryBytes: number
  sampledAt: string
}
type ResourceUsage = {
  state: string
  reason: string | null
  observedAt: string
  totals: { cpuMillicores: number; memoryBytes: number } | null
  pods: ResourceUsagePod[]
}
type ResourceInventory = {
  state: string
  reason: string | null
  deployments: {
    name: string
    replicas: number | null
    readyReplicas: number | null
  }[]
}
type ProjectLogs = {
  state: string
  reason: string | null
  lines: { timestamp: string; pod: string; message: string }[]
  truncated: boolean
  nextCursor: string | null
}
type ProjectConfiguration = {
  revision: number
  values: Record<string, string>
  activationState: string
  activationReason: string | null
}
type ProjectSecrets = {
  secrets: {
    name: string
    version: number
    state: string
    changedAt: string | null
  }[]
  activationState: string
  activationReason: string | null
}
type DataServices = {
  services: {
    resourceId: string
    ownerProject: string
    type: string
    name: string
    state: string
    observedState: string
    reason: string | null
  }[]
  bindings: {
    bindingId: string
    resourceId: string
    component: string
    state: string
    observedState: string
    credentialActive: boolean
    reason: string | null
  }[]
  latestRecoveryRequest: {
    reason: string
    status: string
    requestedAt: string
    reviewedAt: string | null
  } | null
}
type DeploymentCredentials = {
  credentials: {
    id: string
    name: string
    status: string
    createdAt: string
    expiresAt: string
    lastUsedAt: string | null
    rotatedFrom: string | null
  }[]
}
type OneTimeDeploymentCredential = {
  clientId: string
  clientSecret: string
  tokenEndpoint: string
}
type ProjectGrant = {
  issuer: string
  subject: string
  displayName: string | null
  role: 'viewer' | 'developer' | 'project-admin'
  grantedAt: string
}
type ProjectGrants = { project: string; grants: ProjectGrant[] }
type PlatformGrant = {
  issuer: string
  subject: string
  displayName: string | null
  role: 'platform-admin'
  grantedAt: string
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function parseProjectList(value: unknown): ProjectSummary[] {
  if (!Array.isArray(value)) {
    throw new Error('The platform returned an invalid project list.')
  }

  return value.map((project) => {
    const record = asRecord(project)
    if (
      !record ||
      typeof record.name !== 'string' ||
      typeof record.status !== 'string'
    ) {
      throw new Error('The platform returned an invalid project list.')
    }

    return { name: record.name, status: record.status }
  })
}

function parseProjectRevisions(value: unknown): ProjectRevisions {
  const record = asRecord(value)
  if (
    !record ||
    typeof record.project !== 'string' ||
    !Array.isArray(record.revisions)
  ) {
    throw new Error('The platform returned invalid project revisions.')
  }

  const currentRevision = record.current_revision
  if (currentRevision !== null && typeof currentRevision !== 'number') {
    throw new Error('The platform returned invalid project revisions.')
  }

  return {
    project: record.project,
    currentRevision,
    revisions: record.revisions.map((revision) => {
      const item = asRecord(revision)
      if (
        !item ||
        typeof item.revision !== 'number' ||
        typeof item.created_at !== 'string' ||
        typeof item.current !== 'boolean' ||
        (item.image !== null && typeof item.image !== 'string')
      ) {
        throw new Error('The platform returned invalid project revisions.')
      }

      return {
        revision: item.revision,
        createdAt: item.created_at,
        current: item.current,
        image: item.image,
      }
    }),
  }
}

async function listProjects() {
  const { data, error, response } = await apiClient.GET('/v1/projects')
  if (error) {
    throw apiErrorFromResponse(response, error)
  }

  return parseProjectList(data)
}

async function createEmptyProject(body: EmptyProjectCreate) {
  const { error, response } = await apiClient.POST('/v1/projects', { body })
  if (error) {
    throw apiErrorFromResponse(response, error)
  }
}

async function getProjectRevisions(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/revisions',
    {
      params: { path: { project: name } },
    },
  )
  if (error) {
    throw apiErrorFromResponse(response, error)
  }

  return parseProjectRevisions(data)
}

async function deployProject(name: string, body: ProjectDeployment) {
  // Read the complete declaration so the simple form preserves other components,
  // their bindings and configuration. The observed ETag prevents lost updates.
  const current = await apiClient.GET('/v1/projects/{project}/application', {
    params: { path: { project: name } },
  })
  if (current.error && current.response.status !== 404) {
    throw apiErrorFromResponse(current.response, current.error)
  }
  const application = current.data ?? {
    apiVersion: 'platform.eseidinger.de/v1' as const,
    kind: 'Application' as const,
    metadata: { name },
    spec: {
      components: [
        {
          name: 'web',
          type: 'service' as const,
          replicas: 1,
          exposure: 'private' as const,
          runtime: { type: 'container' as const, image: body.image },
          ports: [{ name: 'http', protocol: 'http' as const, port: body.port }],
        },
      ],
    },
  }
  const serviceIndex = application.spec.components.findIndex(
    (component) => component.type === 'service',
  )
  if (serviceIndex < 0)
    throw new Error(
      'This application contains scheduled components only. Deploy its complete declaration with the CLI.',
    )
  application.spec.components = application.spec.components.map(
    (component, index) => {
      if (index !== serviceIndex || component.type !== 'service')
        return component
      const ports = component.ports?.length
        ? component.ports.map((port, index) =>
            index === 0 ? { ...port, port: body.port } : port,
          )
        : [{ name: 'http', protocol: 'http' as const, port: body.port }]
      return {
        ...component,
        runtime: { ...component.runtime, image: body.image },
        ports,
        health: { readiness: { profile: body.probe_profile } },
      }
    },
  )
  const { data, error, response } = await apiClient.PUT(
    '/v1/projects/{project}/application',
    {
      params: {
        path: { project: name },
        header: { 'If-Match': current.response.headers.get('ETag') ?? '0' },
      },
      body: application,
    },
  )
  if (error) {
    throw apiErrorFromResponse(response, error)
  }
  const record = asRecord(data)
  if (
    !record ||
    typeof record.operation_id !== 'string' ||
    typeof record.state !== 'string' ||
    typeof record.revision !== 'number'
  ) {
    throw new Error('The platform returned an invalid deployment operation.')
  }
  return {
    operationId: record.operation_id,
    state: record.state,
    revision: record.revision,
  }
}

async function rollbackProject(
  name: string,
  revision: number,
  expectedRevision: number,
) {
  const { data, error, response } = await apiClient.POST(
    '/v1/projects/{project}/rollback',
    {
      params: {
        path: { project: name },
        header: { 'if-match': String(expectedRevision) },
      },
      body: { revision },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.operation_id !== 'string' ||
    typeof record.state !== 'string' ||
    typeof record.revision !== 'number'
  ) {
    throw new Error('The platform returned an invalid rollback operation.')
  }
  return {
    operationId: record.operation_id,
    state: record.state,
    revision: record.revision,
  }
}

async function restartProject(name: string) {
  const { data, error, response } = await apiClient.POST(
    '/v1/projects/{project}/restart',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.operation_id !== 'string' ||
    typeof record.state !== 'string' ||
    typeof record.revision !== 'number'
  ) {
    throw new Error('The platform returned an invalid restart operation.')
  }
  return {
    operationId: record.operation_id,
    state: record.state,
    revision: record.revision,
  }
}

async function getOperation(operationId: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/operations/{operation_id}',
    { params: { path: { operation_id: operationId } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const readiness =
    record &&
    (asRecord(record.readiness) ?? { state: 'not_applicable', reason: null })
  if (
    !record ||
    !readiness ||
    typeof record.state !== 'string' ||
    (record.revision !== undefined && typeof record.revision !== 'number') ||
    (record.error_code !== null && typeof record.error_code !== 'string') ||
    typeof readiness.state !== 'string' ||
    (readiness.reason != null && typeof readiness.reason !== 'string')
  ) {
    throw new Error('The platform returned an invalid operation status.')
  }
  return {
    state: record.state,
    revision: typeof record.revision === 'number' ? record.revision : 0,
    errorCode: record.error_code,
    readinessState: readiness.state,
    readinessReason:
      typeof readiness.reason === 'string' ? readiness.reason : null,
  }
}

async function getResourceUsage(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/resource-usage',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const totals = record && asRecord(record.totals)
  if (
    !record ||
    typeof record.state !== 'string' ||
    (record.reason !== null && typeof record.reason !== 'string') ||
    typeof record.observed_at !== 'string' ||
    !Array.isArray(record.pods) ||
    (record.totals !== null &&
      (!totals ||
        typeof totals.cpu_millicores !== 'number' ||
        typeof totals.memory_bytes !== 'number'))
  ) {
    throw new Error('The platform returned invalid resource usage.')
  }
  const pods = record.pods.map((pod) => {
    const item = asRecord(pod)
    if (
      !item ||
      typeof item.name !== 'string' ||
      typeof item.cpu_millicores !== 'number' ||
      typeof item.memory_bytes !== 'number' ||
      typeof item.sampled_at !== 'string'
    ) {
      throw new Error('The platform returned invalid resource usage.')
    }
    return {
      name: item.name,
      cpuMillicores: item.cpu_millicores,
      memoryBytes: item.memory_bytes,
      sampledAt: item.sampled_at,
    }
  })
  return {
    state: record.state,
    reason: record.reason,
    observedAt: record.observed_at,
    totals: totals
      ? {
          cpuMillicores: totals.cpu_millicores as number,
          memoryBytes: totals.memory_bytes as number,
        }
      : null,
    pods,
  }
}

async function getResourceInventory(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/inventory',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.state !== 'string' ||
    (record.reason !== null && typeof record.reason !== 'string') ||
    !Array.isArray(record.deployments)
  )
    throw new Error('The platform returned invalid resource inventory.')
  const deployments = record.deployments.map((deployment) => {
    const item = asRecord(deployment)
    if (
      !item ||
      typeof item.name !== 'string' ||
      (item.replicas !== null && typeof item.replicas !== 'number') ||
      (item.ready_replicas !== null && typeof item.ready_replicas !== 'number')
    )
      throw new Error('The platform returned invalid resource inventory.')
    return {
      name: item.name,
      replicas: item.replicas,
      readyReplicas: item.ready_replicas,
    }
  })
  return { state: record.state, reason: record.reason, deployments }
}

type ProjectLogFilters = {
  tail: number
  search?: string
  component?: string
  instance?: string
  sinceSeconds?: number
  after?: string
}

async function getProjectLogs(name: string, filters: ProjectLogFilters) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/logs',
    {
      params: {
        path: { project: name },
        query: {
          tail: filters.tail,
          ...(filters.search ? { search: filters.search } : {}),
          ...(filters.component ? { component: filters.component } : {}),
          ...(filters.instance ? { instance: filters.instance } : {}),
          ...(filters.sinceSeconds
            ? { since_seconds: filters.sinceSeconds }
            : {}),
          ...(filters.after ? { after: filters.after } : {}),
        },
      },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.state !== 'string' ||
    (record.reason !== null && typeof record.reason !== 'string') ||
    !Array.isArray(record.lines) ||
    typeof record.truncated !== 'boolean' ||
    (record.next_cursor !== null && typeof record.next_cursor !== 'string')
  )
    throw new Error('The platform returned invalid project logs.')
  const lines = record.lines.map((line) => {
    const item = asRecord(line)
    if (
      !item ||
      typeof item.timestamp !== 'string' ||
      typeof item.pod !== 'string' ||
      typeof item.message !== 'string'
    )
      throw new Error('The platform returned invalid project logs.')
    return { timestamp: item.timestamp, pod: item.pod, message: item.message }
  })
  return {
    state: record.state,
    reason: record.reason,
    lines,
    truncated: record.truncated,
    nextCursor: record.next_cursor,
  }
}

async function getProjectConfiguration(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/configuration',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const values = record && asRecord(record.values)
  const activation = record && asRecord(record.activation)
  if (
    !record ||
    !values ||
    !activation ||
    typeof record.revision !== 'number' ||
    typeof activation.state !== 'string' ||
    (activation.reason !== null && typeof activation.reason !== 'string')
  )
    throw new Error('The platform returned invalid configuration status.')
  if (Object.values(values).some((value) => typeof value !== 'string'))
    throw new Error('The platform returned invalid configuration status.')
  return {
    revision: record.revision,
    values: Object.fromEntries(
      Object.entries(values).sort(([left], [right]) =>
        left.localeCompare(right),
      ),
    ) as Record<string, string>,
    activationState: activation.state,
    activationReason: activation.reason,
  }
}

async function updateProjectConfiguration(
  name: string,
  values: Record<string, string>,
  expectedRevision: number,
) {
  const { data, error, response } = await apiClient.PUT(
    '/v1/projects/{project}/configuration',
    {
      params: {
        path: { project: name },
        header: { 'if-match': String(expectedRevision) },
      },
      body: { values },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.operation_id !== 'string' ||
    typeof record.state !== 'string' ||
    typeof record.revision !== 'number'
  ) {
    throw new Error('The platform returned an invalid configuration operation.')
  }
  return {
    operationId: record.operation_id,
    state: record.state,
    revision: record.revision,
  }
}

async function getProjectSecrets(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/secrets',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const activation = record && asRecord(record.activation)
  if (
    !record ||
    !activation ||
    !Array.isArray(record.secrets) ||
    typeof activation.state !== 'string' ||
    (activation.reason !== null && typeof activation.reason !== 'string')
  ) {
    throw new Error('The platform returned invalid secret metadata.')
  }
  const secrets = record.secrets.map((secret) => {
    const item = asRecord(secret)
    if (
      !item ||
      typeof item.name !== 'string' ||
      typeof item.version !== 'number' ||
      typeof item.state !== 'string' ||
      (item.changed_at !== null && typeof item.changed_at !== 'string')
    ) {
      throw new Error('The platform returned invalid secret metadata.')
    }
    return {
      name: item.name,
      version: item.version,
      state: item.state,
      changedAt: item.changed_at,
    }
  })
  return {
    secrets,
    activationState: activation.state,
    activationReason: activation.reason,
  }
}

async function setProjectSecret(name: string, secret: string, value: string) {
  const { error, response } = await apiClient.PUT(
    '/v1/projects/{project}/secrets/{secret}',
    {
      params: { path: { project: name, secret } },
      body: { value },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function confirmProjectSecretRotation(name: string, secret: string) {
  const { error, response } = await apiClient.POST(
    '/v1/projects/{project}/secrets/{secret}/confirm',
    { params: { path: { project: name, secret } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function revertProjectSecretRotation(name: string, secret: string) {
  const { error, response } = await apiClient.POST(
    '/v1/projects/{project}/secrets/{secret}/revert',
    { params: { path: { project: name, secret } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function deleteProjectSecret(name: string, secret: string) {
  const { error, response } = await apiClient.DELETE(
    '/v1/projects/{project}/secrets/{secret}',
    { params: { path: { project: name, secret } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function getDataServices(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/data-services',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    !Array.isArray(record.services) ||
    !Array.isArray(record.bindings) ||
    (record.latest_recovery_request !== null &&
      !asRecord(record.latest_recovery_request))
  )
    throw new Error('The platform returned invalid data-service status.')
  const services = record.services.map((service) => {
    const item = asRecord(service)
    if (
      !item ||
      typeof item.resource_id !== 'string' ||
      typeof item.owner_project !== 'string' ||
      typeof item.type !== 'string' ||
      typeof item.name !== 'string' ||
      typeof item.state !== 'string' ||
      typeof item.observed_state !== 'string' ||
      (item.reason !== null && typeof item.reason !== 'string')
    )
      throw new Error('The platform returned invalid data-service status.')
    return {
      resourceId: item.resource_id,
      ownerProject: item.owner_project,
      type: item.type,
      name: item.name,
      state: item.state,
      observedState: item.observed_state,
      reason: item.reason,
    }
  })
  const bindings = record.bindings.map((binding) => {
    const item = asRecord(binding)
    if (
      !item ||
      typeof item.binding_id !== 'string' ||
      typeof item.resource_id !== 'string' ||
      typeof item.component !== 'string' ||
      typeof item.state !== 'string' ||
      typeof item.observed_state !== 'string' ||
      typeof item.credential_active !== 'boolean' ||
      (item.reason !== null && typeof item.reason !== 'string')
    )
      throw new Error('The platform returned invalid data-service status.')
    return {
      bindingId: item.binding_id,
      resourceId: item.resource_id,
      component: item.component,
      state: item.state,
      observedState: item.observed_state,
      credentialActive: item.credential_active,
      reason: item.reason,
    }
  })
  const recovery =
    record.latest_recovery_request === null
      ? null
      : asRecord(record.latest_recovery_request)
  if (
    recovery &&
    (typeof recovery.reason !== 'string' ||
      typeof recovery.status !== 'string' ||
      typeof recovery.requested_at !== 'string' ||
      (recovery.reviewed_at !== null &&
        typeof recovery.reviewed_at !== 'string'))
  )
    throw new Error('The platform returned invalid data-service status.')
  return {
    services,
    bindings,
    latestRecoveryRequest: recovery
      ? {
          reason: recovery.reason as string,
          status: recovery.status as string,
          requestedAt: recovery.requested_at as string,
          reviewedAt: recovery.reviewed_at as string | null,
        }
      : null,
  }
}

async function requestDataServiceRecovery(
  name: string,
  reason: 'unavailable' | 'access' | 'data_integrity' | 'other',
) {
  const { error, response } = await apiClient.POST(
    '/v1/projects/{project}/data-services/recovery-requests',
    { params: { path: { project: name } }, body: { reason } },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function getDeploymentCredentials(name: string) {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/deployment-credentials',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (!record || !Array.isArray(record.credentials))
    throw new Error(
      'The platform returned an invalid deployment credential inventory.',
    )
  const credentials = record.credentials.map((credential) => {
    const item = asRecord(credential)
    if (
      !item ||
      typeof item.credential_id !== 'string' ||
      typeof item.name !== 'string' ||
      typeof item.status !== 'string' ||
      typeof item.created_at !== 'string' ||
      typeof item.expires_at !== 'string' ||
      (item.last_used_at !== null && typeof item.last_used_at !== 'string') ||
      (item.rotated_from !== null && typeof item.rotated_from !== 'string')
    )
      throw new Error(
        'The platform returned an invalid deployment credential inventory.',
      )
    return {
      id: item.credential_id,
      name: item.name,
      status: item.status,
      createdAt: item.created_at,
      expiresAt: item.expires_at,
      lastUsedAt: item.last_used_at,
      rotatedFrom: item.rotated_from,
    }
  })
  return { credentials }
}

async function getProjectGrants(name: string): Promise<ProjectGrants> {
  const { data, error, response } = await apiClient.GET(
    '/v1/projects/{project}/grants',
    { params: { path: { project: name } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.project !== 'string' ||
    !Array.isArray(record.grants)
  )
    throw new Error('The platform returned an invalid project grant list.')
  const grants = record.grants.map((grant) => {
    const item = asRecord(grant)
    if (
      !item ||
      typeof item.issuer !== 'string' ||
      typeof item.subject !== 'string' ||
      (item.display_name !== null && typeof item.display_name !== 'string') ||
      !['viewer', 'developer', 'project-admin'].includes(String(item.role)) ||
      typeof item.granted_at !== 'string'
    ) {
      throw new Error('The platform returned an invalid project grant list.')
    }
    return {
      issuer: item.issuer,
      subject: item.subject,
      displayName: item.display_name,
      role: item.role as ProjectGrant['role'],
      grantedAt: item.granted_at,
    }
  })
  return { project: record.project, grants }
}

async function putProjectGrant(
  name: string,
  grant: Omit<ProjectGrant, 'grantedAt'> & { preferredUsername?: string },
) {
  const { error, response } = await apiClient.PUT(
    '/v1/projects/{project}/grants',
    {
      params: { path: { project: name } },
      body: {
        ...(grant.preferredUsername
          ? { preferred_username: grant.preferredUsername }
          : { issuer: grant.issuer, subject: grant.subject }),
        display_name: grant.displayName,
        role: grant.role,
      },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function deleteProjectGrant(
  name: string,
  grant: Pick<ProjectGrant, 'issuer' | 'subject'>,
) {
  const { error, response } = await apiClient.DELETE(
    '/v1/projects/{project}/grants',
    {
      params: { path: { project: name } },
      body: grant,
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function getPlatformGrants(): Promise<PlatformGrant[]> {
  const { data, error, response } = await apiClient.GET('/v1/platform/grants')
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (!record || !Array.isArray(record.grants))
    throw new Error('The platform returned an invalid platform grant list.')
  return record.grants.map((grant) => {
    const item = asRecord(grant)
    if (
      !item ||
      typeof item.issuer !== 'string' ||
      typeof item.subject !== 'string' ||
      (item.display_name !== null && typeof item.display_name !== 'string') ||
      item.role !== 'platform-admin' ||
      typeof item.granted_at !== 'string'
    ) {
      throw new Error('The platform returned an invalid platform grant list.')
    }
    return {
      issuer: item.issuer,
      subject: item.subject,
      displayName: item.display_name,
      role: 'platform-admin',
      grantedAt: item.granted_at,
    }
  })
}

async function putPlatformGrant(
  grant: Omit<PlatformGrant, 'grantedAt' | 'role'> & {
    preferredUsername?: string
  },
) {
  const { error, response } = await apiClient.PUT('/v1/platform/grants', {
    body: {
      ...(grant.preferredUsername
        ? { preferred_username: grant.preferredUsername }
        : { issuer: grant.issuer, subject: grant.subject }),
      display_name: grant.displayName,
      role: 'platform-admin',
    },
  })
  if (error) throw apiErrorFromResponse(response, error)
}

async function deletePlatformGrant(
  grant: Pick<PlatformGrant, 'issuer' | 'subject'>,
) {
  const { error, response } = await apiClient.DELETE('/v1/platform/grants', {
    body: grant,
  })
  if (error) throw apiErrorFromResponse(response, error)
}

async function createDeploymentCredential(
  name: string,
  body: { name: string; expiresInDays: number },
): Promise<OneTimeDeploymentCredential> {
  const { data, error, response } = await apiClient.POST(
    '/v1/projects/{project}/deployment-credentials',
    {
      params: { path: { project: name } },
      body: { name: body.name, expires_in_days: body.expiresInDays },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.client_id !== 'string' ||
    typeof record.client_secret !== 'string' ||
    typeof record.token_endpoint !== 'string'
  )
    throw new Error('The platform returned an invalid deployment credential.')
  return {
    clientId: record.client_id,
    clientSecret: record.client_secret,
    tokenEndpoint: record.token_endpoint,
  }
}

async function revokeDeploymentCredential(name: string, credentialId: string) {
  const { error, response } = await apiClient.DELETE(
    '/v1/projects/{project}/deployment-credentials/{credential_id}',
    { params: { path: { project: name, credential_id: credentialId } } },
  )
  if (error) throw apiErrorFromResponse(response, error)
}

async function rotateDeploymentCredential(
  name: string,
  credentialId: string,
  body: { expiresInDays: number; overlapHours: number },
): Promise<OneTimeDeploymentCredential> {
  const { data, error, response } = await apiClient.POST(
    '/v1/projects/{project}/deployment-credentials/{credential_id}/rotate',
    {
      params: { path: { project: name, credential_id: credentialId } },
      body: {
        expires_in_days: body.expiresInDays,
        overlap_hours: body.overlapHours,
      },
    },
  )
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (
    !record ||
    typeof record.client_id !== 'string' ||
    typeof record.client_secret !== 'string' ||
    typeof record.token_endpoint !== 'string'
  )
    throw new Error(
      'The platform returned an invalid rotated deployment credential.',
    )
  return {
    clientId: record.client_id,
    clientSecret: record.client_secret,
    tokenEndpoint: record.token_endpoint,
  }
}

export {
  confirmProjectSecretRotation,
  createDeploymentCredential,
  createEmptyProject,
  deletePlatformGrant,
  deleteProjectGrant,
  deleteProjectSecret,
  deployProject,
  getDataServices,
  getDeploymentCredentials,
  getOperation,
  getPlatformGrants,
  getProjectConfiguration,
  getProjectGrants,
  getProjectLogs,
  getProjectRevisions,
  getProjectSecrets,
  getResourceInventory,
  getResourceUsage,
  listProjects,
  parseProjectList,
  parseProjectRevisions,
  putPlatformGrant,
  putProjectGrant,
  requestDataServiceRecovery,
  restartProject,
  revertProjectSecretRotation,
  revokeDeploymentCredential,
  rollbackProject,
  rotateDeploymentCredential,
  setProjectSecret,
  updateProjectConfiguration,
}
export type {
  DataServices,
  DeploymentCredentials,
  EmptyProjectCreate,
  OneTimeDeploymentCredential,
  OperationAccepted,
  OperationStatus,
  PlatformGrant,
  ProjectConfiguration,
  ProjectDeployment,
  ProjectGrant,
  ProjectGrants,
  ProjectLogs,
  ProjectRevision,
  ProjectRevisions,
  ProjectSecrets,
  ProjectSummary,
  ResourceInventory,
  ResourceUsage,
}
