import type { Page } from '@playwright/test'

type Row = {
  id: string
  kind: string
  name: string
  project: string
  state: string
  version: number
  spec: Record<string, unknown>
  created_at: string
  updated_at: string
}
type Operation = {
  id: string
  resourceId: string
  resourceVersion: number
  action: string
  state: string
  attempts: number
  errorCode: string | null
  createdAt: string
  updatedAt: string
  canRetry: boolean
}
export async function accessFixture(
  page: Page,
  options: {
    manage?: boolean
    consume?: boolean
    withPolicy?: boolean
    unavailable?: string
    eligible?: boolean
  } = {},
) {
  const created = '2026-10-12T12:00:00Z'
  let serial = 0
  function row(
    kind: string,
    name: string,
    project: string,
    spec: Record<string, unknown>,
    state = 'active',
  ): Row {
    return {
      id: `${kind}_${++serial}`,
      kind,
      name,
      project,
      spec,
      state,
      version: 1,
      created_at: created,
      updated_at: created,
    }
  }
  const readers = row('group', 'readers', 'provider', {
    displayName: 'Readers',
  })
  readers.id = 'grp_readers'
  const groups: Row[] = [readers]
  const policyBody = {
    component: 'api',
    defaultDecision: 'deny',
    identityAttributes: { displayName: false, email: false },
    routes: [
      {
        name: 'interactive',
        match: { pathPrefix: '/app/', methods: ['GET', 'POST'] },
        authentication: { mode: 'browser-session' },
        authorization: { anyOfGroups: [readers.id] },
      },
      {
        name: 'machine',
        match: { pathPrefix: '/api/', methods: ['GET'] },
        authentication: { mode: 'bearer-token' },
        authorization: { anyOfGroups: [readers.id] },
      },
    ],
    host: 'api-provider.apps.test',
    revisionId: 'rev_initial',
    previousRevision: null,
  }
  let policy: Row | null =
    options.withPolicy === false
      ? null
      : row('policy', 'provider', 'provider', policyBody)
  if (policy) policy.id = 'pol_provider'
  let governance: Row | null = null
  const humans: Row[] = [
    row(
      'human-request',
      'human',
      'provider',
      {
        policyId: 'pol_provider',
        principalId: 'prn_person',
        issuer: 'https://identity.test/realms/platform',
        subject: 'person',
        expiresAt: new Date(Date.now() + 30 * 86400_000).toISOString(),
      },
      'pending',
    ),
  ]
  const memberships: Row[] = []
  const services: Row[] = [
    row(
      'service-access',
      'provider-reader',
      'consumer',
      {
        providerProject: 'provider',
        application: 'provider',
        projectWideCredential: true,
        policyId: 'pol_provider',
        principalId: 'prn_service',
        groups: [],
        credentials: [],
      },
      'pending',
    ),
  ]
  const operations: Operation[] = []
  const tasks = new Map<string, { ticks: number; finish: () => void }>()
  const mutations: {
    method: string
    path: string
    body: unknown
    headers: Record<string, string>
  }[] = []
  function schedule(resource: Row, action: string, finish: () => void) {
    const op: Operation = {
      id: `operation_${++serial}`,
      resourceId: resource.id,
      resourceVersion: resource.version,
      action,
      state: 'running',
      attempts: 1,
      errorCode: null,
      createdAt: created,
      updatedAt: created,
      canRetry: false,
    }
    operations.push(op)
    tasks.set(op.id, { ticks: 0, finish })
    return op.id
  }
  await page.route('**/projects/*/components', (route) =>
    route.fulfill({
      json: {
        components: [
          {
            name: 'api',
            type: 'service',
            status: { state: 'ready', reason: null },
          },
        ],
      },
    }),
  )
  await page.route('**/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const body: Record<string, unknown> = JSON.parse(
      request.postData() ?? '{}',
    ) as Record<string, unknown>
    const project = path.split('/')[3] ?? 'provider'
    const manage = options.manage ?? true
    const consume = options.consume ?? true
    const send = (data: unknown, status = 200) =>
      route.fulfill({ json: data, status })
    if (method !== 'GET')
      mutations.push({ method, path, body, headers: request.headers() })
    if (path === '/v1/capabilities')
      return send({
        hostedApplicationAccess: {
          modes: ['browser-session', 'bearer-token'],
          requires: 'platform.example/v1alpha2',
          authorization: 'anyOfGroups',
          maxAuthorizationStalenessSeconds: 300,
          credentialIsolation: 'project',
        },
      })
    if (path.endsWith('/application-access-context'))
      return send({
        project,
        application: project,
        status: 'applied',
        eligible: options.eligible ?? true,
        reason:
          options.eligible === false
            ? 'Deploy a v1alpha2 application before configuring access'
            : null,
        component: options.eligible === false ? null : 'api',
        url:
          options.eligible === false
            ? null
            : `https://api-${project}.apps.test`,
        permissions: { manage, consume },
      })
    if (method === 'GET' && path.endsWith('/application-access-operations')) {
      for (const op of operations) {
        const task = tasks.get(op.id)
        if (task && ++task.ticks > 1) {
          task.finish()
          op.state = 'succeeded'
          tasks.delete(op.id)
        }
      }
      return send({ items: operations, limit: 100 })
    }
    if (path.endsWith('/governance')) {
      if (method === 'GET')
        return governance
          ? send(governance)
          : send({ detail: 'Project governance is not recorded' }, 404)
      if (!manage) return send({ detail: 'Access denied' }, 403)
      governance = row('governance', 'project', project, body)
      return send(governance)
    }
    if (path.endsWith('/application-groups')) {
      if (method === 'GET') return send({ items: groups })
      if (!manage) return send({ detail: 'Access denied' }, 403)
      const group = row('group', String(body.name), project, {
        displayName: String(body.displayName),
      })
      groups.push(group)
      return send(group, 201)
    }
    if (path.endsWith('/access-policy/revisions'))
      return send({
        items: policy
          ? [{ ...policy, id: policy.spec.revisionId, kind: 'policy-revision' }]
          : [],
      })
    if (path.endsWith('/access-policy')) {
      if (method === 'GET') {
        if (options.unavailable === 'policy')
          return send({ detail: 'Policy storage unavailable' }, 503)
        return policy
          ? send(policy)
          : send({ detail: 'Access policy is not configured' }, 404)
      }
      if (!manage) return send({ detail: 'Access denied' }, 403)
      policy = {
        ...row(
          'policy',
          'provider',
          project,
          {
            ...body,
            host: 'api-provider.apps.test',
            revisionId: 'rev_new',
            previousRevision: null,
          },
          'provisioning',
        ),
        id: 'pol_provider',
      }
      const saved = policy
      const operation_id = schedule(saved, 'policy.apply', () => {
        saved.state = 'active'
        saved.version++
      })
      return send({ ...saved, operation_id }, 202)
    }
    if (path.endsWith('/application-access-requests')) {
      if (!manage) return send({ detail: 'Access denied' }, 403)
      if (options.unavailable === 'humans')
        return send({ detail: 'Requests unavailable' }, 503)
      return send({ items: humans })
    }
    if (path.includes('/application-access-requests/')) {
      if (!manage) return send({ detail: 'Access denied' }, 403)
      const human = humans.find((r) => path.includes(r.id))
      if (!human) return send({ detail: 'Unknown request' }, 404)
      if (request.headers()['if-match'] !== `"${human.version}"`)
        return send({ detail: 'Access resource version changed' }, 412)
      const action = path.split('/').at(-1)
      human.version++
      if (action === 'approve' || action === 'groups') {
        human.state = 'approved'
        for (const groupId of body.groups as string[]) {
          const member = row(
            'membership',
            'member',
            'provider',
            {
              policyId: 'pol_provider',
              principalId: 'prn_person',
              issuer: 'https://identity.test/realms/platform',
              subject: 'person',
              groupId,
            },
            'provisioning',
          )
          memberships.push(member)
          schedule(member, 'membership.grant', () => {
            member.state = 'active'
            member.version++
          })
        }
      } else
        human.state =
          action === 'reopen'
            ? 'pending'
            : action === 'reject'
              ? 'rejected'
              : 'cancelled'
      return send(
        human,
        action === 'approve' || action === 'groups' ? 202 : 200,
      )
    }
    if (path.endsWith('/application-group-memberships'))
      return manage
        ? send({ items: memberships })
        : send({ detail: 'Access denied' }, 403)
    if (
      path.includes('/application-group-memberships/') &&
      method === 'DELETE'
    ) {
      if (!manage) return send({ detail: 'Access denied' }, 403)
      const member = memberships.find((r) => path.endsWith(r.id))
      if (!member) return send({ detail: 'Unknown membership' }, 404)
      member.state = 'revocation-pending'
      member.version++
      const operation_id = schedule(member, 'membership.revoke', () => {
        member.state = 'revoked'
        member.version++
      })
      return send({ ...member, operation_id }, 202)
    }
    if (path.endsWith('/service-access-requests')) {
      if (method === 'GET')
        return send({
          items: services.filter(
            (r) => r.project === project || r.spec.providerProject === project,
          ),
        })
      if (!consume) return send({ detail: 'Access denied' }, 403)
      const service = row(
        'service-access',
        String(body.name),
        project,
        {
          ...body,
          policyId: 'pol_provider',
          principalId: 'prn_newservice',
          groups: [],
          credentials: [],
        },
        'pending',
      )
      services.push(service)
      return send(service, 201)
    }
    if (path.includes('/service-access-requests/')) {
      const service = services.find((r) => path.includes(r.id))
      if (!service) return send({ detail: 'Unknown service' }, 404)
      const action = method === 'DELETE' ? 'revoke' : path.split('/').at(-1)
      if (
        action === 'approve' || action === 'reject'
          ? !manage
          : !consume && !manage
      )
        return send({ detail: 'Access denied' }, 403)
      if (request.headers()['if-match'] !== `"${service.version}"`)
        return send({ detail: 'Access resource version changed' }, 412)
      service.version++
      if (action === 'approve') {
        service.state = 'provisioning'
        service.spec.groups = body.groups
        const operation_id = schedule(service, 'service.provision', () => {
          service.state = 'active'
          service.version++
          Object.assign(service.spec, {
            secretPrefix: 'ACCESS_FIXTURE',
            audience: 'app_provider',
            providerUrl: 'https://api-provider.apps.test',
            credentials: [
              {
                id: 'credential_1',
                state: 'active',
                secret: 'MUST-NOT-RENDER',
              },
            ],
          })
        })
        return send({ ...service, operation_id }, 202)
      }
      if (action === 'rotate') {
        const emergency = body.emergency === true
        service.spec.credentials = [
          {
            id: 'credential_1',
            state: emergency ? 'revocation-pending' : 'overlap',
            expiresAt: new Date(Date.now() + 86400_000).toISOString(),
          },
          { id: 'credential_2', state: 'provisioning' },
        ]
        const operation_id = schedule(service, 'service.rotate', () => {
          service.version++
          service.spec.credentials = [
            {
              id: 'credential_1',
              state: emergency ? 'revoked' : 'overlap',
              expiresAt: new Date(Date.now() + 86400_000).toISOString(),
            },
            { id: 'credential_2', state: 'active' },
          ]
        })
        return send({ ...service, operation_id }, 202)
      }
      if (action === 'confirm') {
        service.spec.adoption = 'confirmed'
        service.spec.credentials = [
          { id: 'credential_1', state: 'revoked' },
          { id: 'credential_2', state: 'active' },
        ]
        return send(service, 202)
      }
      service.state =
        action === 'reject'
          ? 'rejected'
          : action === 'cancel'
            ? 'cancelled'
            : 'revocation-pending'
      const operation_id =
        action === 'revoke'
          ? schedule(service, 'service.revoke', () => {
              service.state = 'revoked'
              service.version++
            })
          : undefined
      return send({ ...service, operation_id })
    }
    return send({ detail: 'Fixture route is unsupported' }, 404)
  })
  return {
    mutations,
    groups,
    humans,
    memberships,
    services,
    getPolicy: () => policy,
  }
}
