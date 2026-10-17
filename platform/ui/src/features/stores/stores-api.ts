import { z } from 'zod'
import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'
import type { components } from '@/api/generated/schema'

const resource = z.object({ resource_id: z.uuid(), owner_project: z.string(), name: z.string(), provider: z.string(),
  state: z.string(), observed_state: z.string(), version: z.number(), quota_bytes: z.number(),
  used_bytes: z.number().nullable().optional(), usage_measured_at: z.string().nullable().optional(), usage_error: z.boolean().optional(),
  extensions: z.array(z.string()), console_url: z.string().nullable().optional(), error_code: z.string().nullable() })
const grant = z.object({ grant_id: z.uuid(), resource_id: z.uuid(), kind: z.enum(['human', 'binding']), issuer: z.string().nullable(), subject: z.string().nullable(),
  consumer_project: z.string().nullable(), component: z.string().nullable(), mode: z.enum(['read-only', 'read-write']),
  state: z.string(), observed_state: z.string(), version: z.number(), error_code: z.string().nullable() })
const credential = z.object({ credential_id: z.uuid(), grant_id: z.uuid(), state: z.string(), expires_at: z.string(), issued_at: z.string(),
  connection: z.record(z.string(), z.string()).optional(), provider: z.string().optional(),
  ssh: z.object({ user: z.string(), host: z.string(), port: z.number(), destination: z.string(), destination_port: z.number() }).optional() })
const leaseMetadata = credential.omit({ connection: true, ssh: true })
const context = z.object({ manage: z.boolean(), platform_admin: z.boolean(), providers: z.array(z.object({ id: z.string(), enabled: z.boolean() })) })
const preview = z.object({ resource_id: z.uuid(), owner_project: z.string(), name: z.string(), version: z.number(), effect: z.string() })
export type Resource = z.infer<typeof resource>
export type Provider = components['schemas']['ResourceCreate']['provider']
export type Grant = z.infer<typeof grant>
export type Credential = z.infer<typeof credential>
export type Preview = z.infer<typeof preview>
type Schema = components['schemas']
type Result = { data?: unknown; error?: unknown; response: Response }
function checked(result: Result) {
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error)
  return result.data
}
export const getContext = async (project: string) => context.parse(checked(await apiClient.GET('/v1/projects/{project}/store-context', { params: { path: { project } } })))
export const getResources = async (project: string) => z.object({ resources: z.array(resource) }).parse(checked(await apiClient.GET('/v1/projects/{project}/resources', { params: { path: { project } } }))).resources
export const getBindings = async (project: string) => z.object({ bindings: z.array(grant) }).parse(checked(await apiClient.GET('/v1/projects/{project}/resource-bindings', { params: { path: { project } } }))).bindings
export const getGrants = async (resource_id: string) => z.object({ grants: z.array(grant) }).parse(checked(await apiClient.GET('/v1/resources/{resource_id}/grants', { params: { path: { resource_id } } }))).grants
export const getMine = async () => z.object({ grants: z.array(z.object({ grant, resource })) }).parse(checked(await apiClient.GET('/v1/store-access/me'))).grants
export const createResource = async (project: string, body: Schema['ResourceCreate']) => checked(await apiClient.POST('/v1/projects/{project}/resources', { params: { path: { project } }, body }))
export const renameResource = async (resource_id: string, body: Schema['ResourceRename']) => checked(await apiClient.PATCH('/v1/resources/{resource_id}', { params: { path: { resource_id } }, body }))
export const quota = async (resource_id: string, body: Schema['QuotaChange']) => checked(await apiClient.PUT('/v1/resources/{resource_id}/quota', { params: { path: { resource_id } }, body }))
export const retireResource = async (resource_id: string, version: number) => checked(await apiClient.POST('/v1/resources/{resource_id}/retirement', { params: { path: { resource_id } }, body: { version } }))
export const getPreview = async (resource_id: string) => preview.parse(checked(await apiClient.GET('/v1/resources/{resource_id}/purge-preview', { params: { path: { resource_id } } })))
export const purgeResource = async (row: Preview) => checked(await apiClient.POST('/v1/resources/{resource_id}/purge', { params: { path: { resource_id: row.resource_id } }, body: { version: row.version, confirm_resource_id: row.resource_id, confirm_owner_project: row.owner_project } }))
export const createHuman = async (resource_id: string, body: Schema['HumanGrant']) => checked(await apiClient.POST('/v1/resources/{resource_id}/human-grants', { params: { path: { resource_id } }, body }))
export const requestBinding = async (project: string, body: Schema['BindingRequest']) => checked(await apiClient.POST('/v1/projects/{project}/resource-bindings', { params: { path: { project } }, body }))
export const approve = async (row: Grant, approved: boolean) => checked(await apiClient.POST('/v1/resource-grants/{grant_id}/approval', { params: { path: { grant_id: row.grant_id } }, body: { version: row.version, approve: approved } }))
export const revoke = async (row: Grant) => checked(await apiClient.POST('/v1/resource-grants/{grant_id}/revocation', { params: { path: { grant_id: row.grant_id } }, body: { version: row.version } }))
export const mode = async (row: Grant, next: Schema['GrantUpdate']['mode']) => checked(await apiClient.PUT('/v1/resource-grants/{grant_id}/mode', { params: { path: { grant_id: row.grant_id } }, body: { version: row.version, mode: next } }))
export const key = async (public_key: string) => checked(await apiClient.PUT('/v1/store-access/me/key', { body: { public_key } }))
export const issue = async (grant_id: string) => leaseMetadata.parse(checked(await apiClient.POST('/v1/store-access/{grant_id}/credentials', { params: { path: { grant_id } } })))
export const reveal = async (credential_id: string) => credential.parse(checked(await apiClient.GET('/v1/store-access/credentials/{credential_id}', { params: { path: { credential_id } } })))
export const leases = async (grant_id: string) => z.object({ credentials: z.array(leaseMetadata) }).parse(checked(await apiClient.GET('/v1/store-access/{grant_id}/credentials', { params: { path: { grant_id } } }))).credentials
