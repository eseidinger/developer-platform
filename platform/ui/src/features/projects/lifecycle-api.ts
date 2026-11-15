import { z } from 'zod'
import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'

export type LifecycleAction = 'retire' | 'restore' | 'purge'
const previewSchema = z.object({
  project: z.string(),
  project_id: z.uuid(),
  status: z.string(),
  action: z.enum(['retire', 'restore', 'purge']),
  inventory: z
    .object({
      workloads: z.array(z.object({ kind: z.string(), name: z.string() })),
      named_store_resources: z.array(
        z.object({ name: z.string(), provider: z.string() }),
      ),
      named_store_grants: z.array(z.unknown()),
    })
    .passthrough(),
  blockers: z.array(z.string()),
  scope_token: z.string(),
})
export type LifecyclePreview = z.infer<typeof previewSchema>
const acceptedSchema = z.object({
  operation_id: z.uuid(),
  state: z.string(),
  status_url: z.string(),
})

export async function getLifecyclePreview(
  project: string,
  action: LifecycleAction,
) {
  const params = { path: { project } }
  const result =
    action === 'retire'
      ? await apiClient.GET('/v1/projects/{project}/retirement-preview', {
          params,
        })
      : action === 'restore'
        ? await apiClient.GET(
            '/v1/operator/projects/{project}/restore-preview',
            { params },
          )
        : await apiClient.GET('/v1/operator/projects/{project}/purge-preview', {
            params,
          })
  if (result.error) throw apiErrorFromResponse(result.response, result.error)
  return previewSchema.parse(result.data)
}

export async function startLifecycle(preview: LifecyclePreview) {
  const options = {
    params: { path: { project: preview.project } },
    body: {
      confirm_name: preview.project,
      confirm_project_id: preview.project_id,
      scope_token: preview.scope_token,
    },
  }
  const result =
    preview.action === 'retire'
      ? await apiClient.POST('/v1/projects/{project}/retire', options)
      : preview.action === 'restore'
        ? await apiClient.POST(
            '/v1/operator/projects/{project}/restore',
            options,
          )
        : await apiClient.POST('/v1/operator/projects/{project}/purge', options)
  if (result.error) throw apiErrorFromResponse(result.response, result.error)
  return acceptedSchema.parse(result.data)
}
