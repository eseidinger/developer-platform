import type { Page, Route } from '@playwright/test'

type Mutation = {
  method: string
  path: string
  body: Record<string, unknown>
  ifMatch: string | null
}

export async function projectFixture(
  page: Page,
  options: { denyCreate?: boolean } = {},
) {
  const mutations: Mutation[] = []
  const unexpected: string[] = []
  let exists = false
  let retired = false
  let revision = 0
  let operationRevision = 0
  const image = 'hashicorp/http-echo:1.0.0'
  const createdAt = '2026-10-18T12:00:00Z'
  const send = (route: Route, data: unknown, status = 200) =>
    route.fulfill({ json: data, status })

  await page.route('**/projects**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!path.startsWith('/projects')) return route.continue()
    const method = request.method()
    const body = request.postDataJSON?.() as Record<string, unknown> | undefined
    if (method !== 'GET')
      mutations.push({
        method,
        path,
        body: body ?? {},
        ifMatch: request.headers()['if-match'] ?? null,
      })
    if (path === '/projects' && method === 'GET')
      return send(
        route,
        exists
          ? [{ name: 'demo', status: retired ? 'retired' : 'active' }]
          : [],
      )
    if (path === '/projects' && method === 'POST') {
      if (options.denyCreate)
        return send(route, { detail: 'Project creation denied' }, 403)
      if (body?.name !== 'demo')
        return send(route, { detail: 'Invalid fixture project' }, 400)
      exists = true
      return send(route, { name: 'demo', status: 'active' }, 201)
    }
    if (!exists || !path.startsWith('/projects/demo'))
      return send(route, { detail: 'Unknown project' }, 404)
    if (path === '/projects/demo/revisions')
      return send(route, {
        project: 'demo',
        current_revision: revision || null,
        revisions: Array.from({ length: revision }, (_, index) => ({
          revision: index + 1,
          created_at: createdAt,
          current: index + 1 === revision,
          image,
        })).reverse(),
      })
    if (path === '/projects/demo' && method === 'PUT') {
      if (body?.name !== 'demo' || body?.image !== image || body?.port !== 5678)
        return send(route, { detail: 'Invalid deployment' }, 400)
      operationRevision = ++revision
      return send(
        route,
        {
          operation_id: '11111111-1111-4111-8111-111111111111',
          state: 'queued',
          revision,
        },
        202,
      )
    }
    if (path === '/projects/demo/rollback' && method === 'POST') {
      if (
        request.headers()['if-match'] !== String(revision) ||
        body?.revision !== 1
      )
        return send(route, { detail: 'Stale revision' }, 409)
      operationRevision = ++revision
      return send(
        route,
        {
          operation_id: '22222222-2222-4222-8222-222222222222',
          state: 'queued',
          revision,
        },
        202,
      )
    }
    if (path === '/projects/demo/retirement-preview')
      return send(route, {
        removes: [{ kind: 'namespace', name: 'project-demo' }],
        retains: { catalog: true },
        blockers: [],
        scope_token: 'fixture-scope',
        access: { named_store_resources: [], named_store_grants: [] },
      })
    if (path === '/projects/demo/retire' && method === 'POST') {
      if (
        body?.confirm_name !== 'demo' ||
        body?.scope_token !== 'fixture-scope'
      )
        return send(route, { detail: 'Invalid retirement scope' }, 409)
      retired = true
      return send(route, { status: 'retired' })
    }
    if (path === '/projects/demo/data-services')
      return send(route, {
        services: [],
        bindings: [],
        latest_recovery_request: null,
      })
    if (path === '/projects/demo/deployment-credentials')
      return send(route, { credentials: [] })
    if (path === '/projects/demo/grants')
      return send(route, { project: 'demo', grants: [] })
    if (path === '/projects/demo/resource-usage')
      return send(route, {
        state: 'ready',
        reason: null,
        observed_at: createdAt,
        totals: { cpu_millicores: 100, memory_bytes: 1048576 },
        pods: [],
      })
    if (path === '/projects/demo/resources')
      return send(route, {
        state: 'ready',
        reason: null,
        deployments: [{ name: 'demo', replicas: 1, ready_replicas: 1 }],
      })
    if (path === '/projects/demo/logs')
      return send(route, {
        state: 'ready',
        reason: null,
        lines: [],
        truncated: false,
        next_cursor: null,
      })
    if (path === '/projects/demo/configuration')
      return send(route, {
        revision,
        values: {},
        activation: { state: 'ready', reason: null },
      })
    if (path === '/projects/demo/secrets')
      return send(route, {
        secrets: [],
        activation: { state: 'ready', reason: null },
      })
    unexpected.push(`${method} ${path}`)
    return send(route, { detail: 'Unmocked project route' }, 404)
  })
  await page.route('**/v1/operations/**', (route) =>
    send(route, {
      state: 'succeeded',
      revision: operationRevision,
      error_code: null,
      readiness: { state: 'ready', reason: null },
    }),
  )
  return { mutations, unexpected, isRetired: () => retired }
}
