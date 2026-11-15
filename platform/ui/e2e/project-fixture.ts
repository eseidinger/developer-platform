import type { Page, Route } from '@playwright/test'

type Mutation = {
  method: string
  path: string
  body: Record<string, unknown>
  ifMatch: string | null
}

export async function projectFixture(
  page: Page,
  options: { denyCreate?: boolean; retired?: boolean } = {},
) {
  const mutations: Mutation[] = []
  const unexpected: string[] = []
  let exists = options.retired ?? false
  let retired = options.retired ?? false
  let revision = options.retired ? 1 : 0
  let operationRevision = 0
  let operationKind = 'deployment'
  let application: unknown = null
  const image = 'hashicorp/http-echo:1.0.0'
  const createdAt = '2026-10-18T12:00:00Z'
  const send = (route: Route, data: unknown, status = 200) =>
    route.fulfill({ json: data, status })

  await page.route('**/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const body = request.postDataJSON?.() as Record<string, unknown> | undefined
    if (method !== 'GET')
      mutations.push({
        method,
        path,
        body: body ?? {},
        ifMatch: request.headers()['if-match'] ?? null,
      })
    if (path === '/v1/projects' && method === 'GET')
      return send(
        route,
        exists
          ? [{ name: 'demo', status: retired ? 'retired' : 'active' }]
          : [],
      )
    if (path === '/v1/projects' && method === 'POST') {
      if (options.denyCreate)
        return send(route, { detail: 'Project creation denied' }, 403)
      if (body?.name !== 'demo')
        return send(route, { detail: 'Invalid fixture project' }, 400)
      exists = true
      return send(route, { name: 'demo', status: 'active' }, 201)
    }
    if (path.startsWith('/v1/operator/projects/demo/')) {
      const action = path.includes('/restore') ? 'restore' : 'purge'
      if (method === 'GET')
        return send(route, {
          project: 'demo',
          project_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          status: 'retired',
          action,
          inventory: {
            workloads: [],
            named_store_resources: [],
            named_store_grants: [],
          },
          blockers: [],
          scope_token: 'fixture-scope',
        })
      if (
        body?.confirm_name !== 'demo' ||
        body.confirm_project_id !== 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' ||
        body.scope_token !== 'fixture-scope'
      )
        return send(route, { detail: 'Scope changed' }, 409)
      operationKind = action
      if (action === 'restore') retired = false
      else exists = false
      return send(
        route,
        {
          operation_id:
            action === 'restore'
              ? '44444444-4444-4444-8444-444444444444'
              : '55555555-5555-4555-8555-555555555555',
          state: 'queued',
          status_url: '/v1/operations/fixture',
        },
        202,
      )
    }
    if (!exists || !path.startsWith('/v1/projects/demo'))
      return send(route, { detail: 'Unknown project' }, 404)
    if (path === '/v1/projects/demo/revisions')
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
    if (path === '/v1/projects/demo/application' && method === 'GET')
      return application
        ? route.fulfill({
            json: application,
            headers: { ETag: String(revision) },
          })
        : send(route, { detail: 'Application missing' }, 404)
    if (path === '/v1/projects/demo/application' && method === 'PUT') {
      if (
        body?.apiVersion !== 'platform.eseidinger.de/v1' ||
        body.kind !== 'Application'
      )
        return send(route, { detail: 'Invalid deployment' }, 400)
      operationKind = 'deployment'
      application = body
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
    if (path === '/v1/projects/demo/rollback' && method === 'POST') {
      if (
        request.headers()['if-match'] !== String(revision) ||
        body?.revision !== 1
      )
        return send(route, { detail: 'Stale revision' }, 409)
      operationKind = 'deployment'
      application = body
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
    if (path === '/v1/projects/demo/retirement-preview')
      return send(route, {
        project: 'demo',
        project_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        status: retired ? 'retired' : 'applied',
        action: 'retire',
        inventory: {
          workloads: [{ kind: 'Namespace', name: 'project-demo' }],
          named_store_resources: [],
          named_store_grants: [],
        },
        blockers: [],
        scope_token: 'fixture-scope',
        access: { named_store_resources: [], named_store_grants: [] },
      })
    if (path === '/v1/projects/demo/retire' && method === 'POST') {
      if (
        body?.confirm_name !== 'demo' ||
        body?.scope_token !== 'fixture-scope' ||
        body.confirm_project_id !== 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
      )
        return send(route, { detail: 'Invalid retirement scope' }, 409)
      retired = true
      operationKind = 'retire'
      return send(
        route,
        {
          operation_id: '33333333-3333-4333-8333-333333333333',
          state: 'queued',
          status_url: '/v1/operations/33333333-3333-4333-8333-333333333333',
        },
        202,
      )
    }
    if (path === '/v1/projects/demo/data-services')
      return send(route, {
        services: [],
        bindings: [],
        latest_recovery_request: null,
      })
    if (path === '/v1/projects/demo/deployment-credentials')
      return send(route, { credentials: [] })
    if (path === '/v1/projects/demo/grants')
      return send(route, { project: 'demo', grants: [] })
    if (path === '/v1/projects/demo/resource-usage')
      return send(route, {
        state: 'ready',
        reason: null,
        observed_at: createdAt,
        totals: { cpu_millicores: 100, memory_bytes: 1048576 },
        pods: [],
      })
    if (path === '/v1/projects/demo/inventory')
      return send(route, {
        state: 'ready',
        reason: null,
        deployments: [{ name: 'demo', replicas: 1, ready_replicas: 1 }],
      })
    if (path === '/v1/projects/demo/logs')
      return send(route, {
        state: 'ready',
        reason: null,
        lines: [],
        truncated: false,
        next_cursor: null,
      })
    if (path === '/v1/projects/demo/configuration')
      return send(route, {
        revision,
        values: {},
        activation: { state: 'ready', reason: null },
      })
    if (path === '/v1/projects/demo/secrets')
      return send(route, {
        secrets: [],
        activation: { state: 'ready', reason: null },
      })
    unexpected.push(`${method} ${path}`)
    return send(route, { detail: 'Unmocked project route' }, 404)
  })
  await page.route('**/v1/operations/**', (route) =>
    send(route, {
      kind: operationKind,
      state: 'succeeded',
      revision: operationRevision,
      error_code: null,
      readiness: { state: 'ready', reason: null },
    }),
  )
  return { mutations, unexpected, isRetired: () => retired }
}
