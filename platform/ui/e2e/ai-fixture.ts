import type { Page } from '@playwright/test'
export const runId = '11111111-1111-4111-8111-111111111111'
export const proposalId = '22222222-2222-4222-8222-222222222222'
export const digest = 'a'.repeat(64)
export async function aiFixture(page: Page, options: { manage?: boolean; admin?: boolean; human?: boolean; eligible?: boolean; runKind?: string; runState?: string; runBase?: number | null; proposalState?: string; expired?: boolean; stale?: boolean; uncertain?: boolean; denied?: boolean; running?: boolean; pagination?: boolean } = {}) {
  const mutations: { method: string; path: string; body: Record<string, unknown> }[] = []
  let classification = options.eligible === false ? 'restricted' : 'internal'
  let revision = options.stale ? 3 : 2
  let created = false
  let state = options.proposalState ?? 'proposed'
  const run = (project: string) => ({ run_id: runId, project, kind: options.runKind ?? 'investigate_incident', state: options.runState ?? (options.running ? 'running' : 'completed'), model: 'synthetic:model', result: { summary: 'A bounded startup diagnosis.', observations: [{ statement: '<script>untrusted()</script> Startup failed.', source_ids: ['E1'] }], hypotheses: [{ statement: 'Likely startup argument failure.', source_ids: ['E1'] }], gaps: ['Impact is not established.'], insufficient_evidence: false }, evidence: [{ id: 'E1', tool: 'get_runtime_status', source: 'project-runtime', state: 'failed', at: '2026-10-16T15:00:00Z' }], tool_calls: 4, estimated_cost_usd: .01414, created_at: '2026-10-16T15:00:00Z', completed_at: options.running ? null : '2026-10-16T15:00:30Z', base_revision: options.runBase === undefined ? 2 : options.runBase })
  const proposal = (project: string) => ({ proposal_id: proposalId, project, run_id: runId, base_revision: 2, target_revision: 1, diff: { action: 'rollback', project, base_revision: 2, target_revision: 1, changed_paths: ['/components'] }, diff_sha256: digest, state, created_at: new Date().toISOString(), approved_at: state !== 'proposed' ? new Date().toISOString() : null, expires_at: state !== 'proposed' ? new Date(Date.now() + (options.expired ? -60000 : 900000)).toISOString() : null, operation_id: state === 'executed' ? '33333333-3333-4333-8333-333333333333' : null, resulting_revision: state === 'executed' ? 3 : null, rollback_plan: 'Review and redeploy the retained base revision if recovery fails.', operation_status_url: state === 'executed' ? '/v1/operations/synthetic' : null, ...(state === 'executed' ? { observation: { operation_state: 'succeeded', readiness: { state: 'ready', ready_replicas: 1, desired_replicas: 1 } } } : {}) })
  await page.route('**/projects/**', async (route) => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname
    if (request.isNavigationRequest() && /^\/projects\/[^/]+\/ai$/.test(path)) return route.fulfill({ response: await route.fetch({ url: new URL('/e2e/ai-harness.html', url).href }) })
    const method = request.method(); const project = path.split('/')[2] ?? 'demo'
    const body = JSON.parse(request.postData() ?? '{}') as Record<string, unknown>
    const send = (data: unknown, status = 200) => route.fulfill({ json: data, status })
    if (method !== 'GET') {
      mutations.push({ method, path, body })
      if (options.denied) return send({ detail: 'Permission changed' }, 403)
    }
    if (path.endsWith('/ai/context')) return send({ project, classification, external_model_eligible: ['public', 'internal'].includes(classification), current_revision: revision, permissions: { run: options.human ?? true, manage: (options.human ?? true) && (options.manage ?? true), edit_policy: (options.human ?? true) && (options.admin ?? false) } })
    if (path.endsWith('/ai/policy')) { classification = String(body.classification); return send({ project, classification }) }
    if (path.endsWith('/ai/runs')) {
      if (method === 'POST') { created = true; if (options.uncertain) return route.abort('failed'); return send({ run_id: runId }) }
      return send({ items: project === 'other' || url.searchParams.has('before') ? [] : [run(project)], next_cursor: options.pagination && !url.searchParams.has('before') ? runId : null })
    }
    if (path.endsWith(`/ai/runs/${runId}`)) return project === 'other' ? send({ detail: 'Unknown project AI run' }, 404) : send(run(project))
    if (path.endsWith('/ai/proposals')) {
      if (method === 'POST') { created = true; return send({ proposal_id: proposalId }) }
      return send({ items: project === 'other' || url.searchParams.has('before') || (!created && !options.proposalState) ? [] : [proposal(project)], next_cursor: null })
    }
    if (path.endsWith('/approval')) { state = 'approved'; return send(proposal(project)) }
    if (path.endsWith('/execute')) { if (state !== 'approved') return send({ detail: 'Approval used' }, 409); state = 'executed'; revision = 3; return send({ state: 'queued' }) }
    if (path.endsWith(`/ai/proposals/${proposalId}`)) return project === 'other' ? send({ detail: 'Unknown project proposal' }, 404) : send(proposal(project))
    return send({ detail: 'Unmocked route' }, 404)
  })
  return { mutations, wasCreated: () => created }
}
