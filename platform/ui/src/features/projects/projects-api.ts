import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'

type ProjectSummary = {
  name: string
  status: string
}

type EmptyProjectCreate = {
  name: string
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

export { createEmptyProject, listProjects, parseProjectList }
export type { EmptyProjectCreate, ProjectSummary }
