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

type OperationAccepted = { operationId: string; state: string; revision: number }
type OperationStatus = { state: string; revision: number; errorCode: string | null; readinessState: string; readinessReason: string | null }
type ResourceUsagePod = { name: string; cpuMillicores: number; memoryBytes: number; sampledAt: string }
type ResourceUsage = { state: string; reason: string | null; observedAt: string; totals: { cpuMillicores: number; memoryBytes: number } | null; pods: ResourceUsagePod[] }
type ResourceInventory = { state: string; reason: string | null; deployments: { name: string; replicas: number | null; readyReplicas: number | null }[] }
type ProjectLogs = { state: string; reason: string | null; lines: { timestamp: string; pod: string; message: string }[]; truncated: boolean }

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
    if (!record || typeof record.name !== 'string' || typeof record.status !== 'string') {
      throw new Error('The platform returned an invalid project list.')
    }

    return { name: record.name, status: record.status }
  })
}

function parseProjectRevisions(value: unknown): ProjectRevisions {
  const record = asRecord(value)
  if (!record || typeof record.project !== 'string' || !Array.isArray(record.revisions)) {
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
  const { data, error, response } = await apiClient.GET('/projects')
  if (error) {
    throw apiErrorFromResponse(response, error)
  }

  return parseProjectList(data)
}

async function createEmptyProject(body: EmptyProjectCreate) {
  const { error, response } = await apiClient.POST('/projects', { body })
  if (error) {
    throw apiErrorFromResponse(response, error)
  }
}

async function getProjectRevisions(name: string) {
  const { data, error, response } = await apiClient.GET('/projects/{name}/revisions', {
    params: { path: { name } },
  })
  if (error) {
    throw apiErrorFromResponse(response, error)
  }

  return parseProjectRevisions(data)
}

async function deployProject(name: string, body: ProjectDeployment) {
  const { data, error, response } = await apiClient.PUT('/projects/{name}', {
    params: { path: { name } },
    body,
  })
  if (error) {
    throw apiErrorFromResponse(response, error)
  }
  const record = asRecord(data)
  if (!record || typeof record.operation_id !== 'string' || typeof record.state !== 'string' || typeof record.revision !== 'number') {
    throw new Error('The platform returned an invalid deployment operation.')
  }
  return { operationId: record.operation_id, state: record.state, revision: record.revision }
}

async function getOperation(operationId: string) {
  const { data, error, response } = await apiClient.GET('/v1/operations/{operation_id}', { params: { path: { operation_id: operationId } } })
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const readiness = record && asRecord(record.readiness)
  if (!record || !readiness || typeof record.state !== 'string' || typeof record.revision !== 'number' || (record.error_code !== null && typeof record.error_code !== 'string') || typeof readiness.state !== 'string' || (readiness.reason !== null && typeof readiness.reason !== 'string')) {
    throw new Error('The platform returned an invalid operation status.')
  }
  return { state: record.state, revision: record.revision, errorCode: record.error_code, readinessState: readiness.state, readinessReason: readiness.reason }
}

async function getResourceUsage(name: string) {
  const { data, error, response } = await apiClient.GET('/projects/{name}/resource-usage', { params: { path: { name } } })
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  const totals = record && asRecord(record.totals)
  if (!record || typeof record.state !== 'string' || (record.reason !== null && typeof record.reason !== 'string') || typeof record.observed_at !== 'string' || !Array.isArray(record.pods) || (record.totals !== null && (!totals || typeof totals.cpu_millicores !== 'number' || typeof totals.memory_bytes !== 'number'))) {
    throw new Error('The platform returned invalid resource usage.')
  }
  const pods = record.pods.map((pod) => {
    const item = asRecord(pod)
    if (!item || typeof item.name !== 'string' || typeof item.cpu_millicores !== 'number' || typeof item.memory_bytes !== 'number' || typeof item.sampled_at !== 'string') {
      throw new Error('The platform returned invalid resource usage.')
    }
    return { name: item.name, cpuMillicores: item.cpu_millicores, memoryBytes: item.memory_bytes, sampledAt: item.sampled_at }
  })
  return { state: record.state, reason: record.reason, observedAt: record.observed_at, totals: totals ? { cpuMillicores: totals.cpu_millicores as number, memoryBytes: totals.memory_bytes as number } : null, pods }
}

async function getResourceInventory(name: string) {
  const { data, error, response } = await apiClient.GET('/projects/{name}/resources', { params: { path: { name } } })
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (!record || typeof record.state !== 'string' || (record.reason !== null && typeof record.reason !== 'string') || !Array.isArray(record.deployments)) throw new Error('The platform returned invalid resource inventory.')
  const deployments = record.deployments.map((deployment) => {
    const item = asRecord(deployment)
    if (!item || typeof item.name !== 'string' || (item.replicas !== null && typeof item.replicas !== 'number') || (item.ready_replicas !== null && typeof item.ready_replicas !== 'number')) throw new Error('The platform returned invalid resource inventory.')
    return { name: item.name, replicas: item.replicas, readyReplicas: item.ready_replicas }
  })
  return { state: record.state, reason: record.reason, deployments }
}

async function getProjectLogs(name: string, tail: number, search: string) {
  const { data, error, response } = await apiClient.GET('/projects/{name}/logs', { params: { path: { name }, query: { tail, ...(search ? { search } : {}) } } })
  if (error) throw apiErrorFromResponse(response, error)
  const record = asRecord(data)
  if (!record || typeof record.state !== 'string' || (record.reason !== null && typeof record.reason !== 'string') || !Array.isArray(record.lines) || typeof record.truncated !== 'boolean') throw new Error('The platform returned invalid project logs.')
  const lines = record.lines.map((line) => { const item = asRecord(line); if (!item || typeof item.timestamp !== 'string' || typeof item.pod !== 'string' || typeof item.message !== 'string') throw new Error('The platform returned invalid project logs.'); return { timestamp: item.timestamp, pod: item.pod, message: item.message } })
  return { state: record.state, reason: record.reason, lines, truncated: record.truncated }
}

export { createEmptyProject, deployProject, getOperation, getProjectLogs, getProjectRevisions, getResourceInventory, getResourceUsage, listProjects, parseProjectList, parseProjectRevisions }
export type { EmptyProjectCreate, OperationAccepted, OperationStatus, ProjectDeployment, ProjectLogs, ProjectRevision, ProjectRevisions, ProjectSummary, ResourceInventory, ResourceUsage }
