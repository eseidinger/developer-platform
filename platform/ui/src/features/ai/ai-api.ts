import { z } from 'zod'
import { apiClient } from '@/api/client'
import { apiErrorFromResponse } from '@/api/errors'

export const kinds = {
  explain_application: 'Explain application',
  investigate_incident: 'Investigate incident',
  development_assistance: 'Development assistance',
} as const
export type RunKind = keyof typeof kinds
export const classifications = ['public', 'internal', 'confidential', 'restricted'] as const
const contextSchema = z.object({
  project: z.string(), classification: z.enum(classifications).nullable(), external_model_eligible: z.boolean(),
  current_revision: z.number().nullable(), permissions: z.object({ run: z.boolean(), manage: z.boolean(), edit_policy: z.boolean() }),
})
const summarySchema = z.object({
  run_id: z.uuid(), project: z.string(), kind: z.enum(['explain_application', 'investigate_incident', 'development_assistance']),
  state: z.enum(['running', 'completed', 'abstained', 'failed']), model: z.string().nullable(),
  tool_calls: z.number(), estimated_cost_usd: z.number().nullable(), created_at: z.string(), completed_at: z.string().nullable(), base_revision: z.number().nullable(),
})
const statement = z.object({ statement: z.string(), source_ids: z.array(z.string()) })
const runSchema = summarySchema.extend({
  result: z.object({ summary: z.string(), observations: z.array(statement).optional(), hypotheses: z.array(statement), gaps: z.array(z.string()), insufficient_evidence: z.boolean(), usage_complete: z.boolean().optional(), pricing_version: z.string().optional() }).nullable(),
  evidence: z.array(z.object({ id: z.string(), tool: z.string(), source: z.string(), state: z.string(), at: z.string() })),
})
const proposalSchema = z.object({
  proposal_id: z.uuid(), project: z.string(), run_id: z.uuid(), base_revision: z.number(), target_revision: z.number(),
  diff: z.object({ action: z.literal('rollback'), project: z.string(), base_revision: z.number(), target_revision: z.number(), changed_paths: z.array(z.string()) }),
  diff_sha256: z.string().regex(/^[a-f0-9]{64}$/), state: z.enum(['proposed', 'approved', 'executed']),
  created_at: z.string(), approved_at: z.string().nullable(), expires_at: z.string().nullable(), operation_id: z.uuid().nullable(), resulting_revision: z.number().nullable(),
  rollback_plan: z.string(), operation_status_url: z.string().nullable(),
  observation: z.object({ operation_state: z.string(), readiness: z.object({ state: z.string(), reason: z.string().nullable().optional(), desired_replicas: z.number().nullable().optional(), ready_replicas: z.number().nullable().optional() }).nullable(), metrics: z.object({ state: z.string(), reason: z.string().optional(), component: z.string().optional(), observed_at: z.string().optional(), window_seconds: z.number().optional(), request_rate_per_second: z.number().nullable().optional(), server_error_rate_per_second: z.number().nullable().optional(), mean_request_duration_seconds: z.number().nullable().optional() }).optional() }).optional(),
})
export type AiContext = z.infer<typeof contextSchema>
export type Run = z.infer<typeof runSchema>
export type Proposal = z.infer<typeof proposalSchema>
export const aiKey = (project: string) => ['ai', project] as const

type ResponseResult = { data?: unknown; error?: unknown; response: Response }
function checked(result: ResponseResult): unknown {
  if (!result.response.ok) throw apiErrorFromResponse(result.response, result.error)
  return result.data
}
function parse<T>(schema: z.ZodType<T>, result: ResponseResult): T {
  const value = schema.safeParse(checked(result))
  if (!value.success) throw new Error('The platform returned an invalid AI response. Refresh history to verify state.')
  return value.data
}
const path = (name: string) => ({ name })
export async function getContext(project: string, signal?: AbortSignal) {
  return parse(contextSchema, await apiClient.GET('/projects/{name}/ai/context', { params: { path: path(project) }, signal }))
}
export async function getRuns(project: string, before: string | undefined, signal?: AbortSignal) {
  return parse(z.object({ items: z.array(summarySchema), next_cursor: z.uuid().nullable() }), await apiClient.GET('/projects/{name}/ai/runs', { params: { path: path(project), query: { before, limit: 20 } }, signal }))
}
export async function getRun(project: string, run_id: string, signal?: AbortSignal) {
  return parse(runSchema, await apiClient.GET('/projects/{name}/ai/runs/{run_id}', { params: { path: { name: project, run_id } }, signal }))
}
export async function getProposals(project: string, before: string | undefined, signal?: AbortSignal) {
  return parse(z.object({ items: z.array(proposalSchema), next_cursor: z.uuid().nullable() }), await apiClient.GET('/projects/{name}/ai/proposals', { params: { path: path(project), query: { before, limit: 20 } }, signal }))
}
export async function getProposal(project: string, proposal_id: string, signal?: AbortSignal) {
  return parse(proposalSchema, await apiClient.GET('/projects/{name}/ai/proposals/{proposal_id}', { params: { path: { name: project, proposal_id } }, signal }))
}
// A timeout can leave a durable run/proposal behind. Callers reconcile GET history; never retry a POST automatically.
export async function createRun(project: string, kind: RunKind) {
  return parse(z.object({ run_id: z.uuid() }), await apiClient.POST('/projects/{name}/ai/runs', { params: { path: path(project) }, body: { kind }, signal: AbortSignal.timeout(120_000) }))
}
export async function createProposal(project: string, run_id: string) {
  return parse(z.object({ proposal_id: z.uuid() }), await apiClient.POST('/projects/{name}/ai/proposals', { params: { path: path(project) }, body: { run_id }, signal: AbortSignal.timeout(120_000) }))
}
export async function approveProposal(project: string, proposal: Proposal) {
  checked(await apiClient.POST('/projects/{name}/ai/proposals/{proposal_id}/approval', { params: { path: { name: project, proposal_id: proposal.proposal_id } }, body: { diff_sha256: proposal.diff_sha256 }, signal: AbortSignal.timeout(120_000) }))
}
export async function executeProposal(project: string, proposal: Proposal) {
  checked(await apiClient.POST('/projects/{name}/ai/proposals/{proposal_id}/execute', { params: { path: { name: project, proposal_id: proposal.proposal_id } }, body: { diff_sha256: proposal.diff_sha256 }, signal: AbortSignal.timeout(120_000) }))
}
export async function setPolicy(project: string, classification: typeof classifications[number]) {
  checked(await apiClient.PUT('/projects/{name}/ai/policy', { params: { path: path(project) }, body: { classification }, signal: AbortSignal.timeout(120_000) }))
}
