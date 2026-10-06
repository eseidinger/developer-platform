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

export { createEmptyProject, getProjectRevisions, listProjects, parseProjectList, parseProjectRevisions }
export type { EmptyProjectCreate, ProjectRevision, ProjectRevisions, ProjectSummary }
