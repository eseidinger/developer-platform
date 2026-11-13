import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { useAuth } from '@/auth/auth-context'
import { isTransientApiError } from '@/api/errors'
import { Button } from '@mantine/core'
import { AccessDialog, RouteSummary } from './access-controls'
import { AccessEvents } from './access-events'
import {
  accessKeys,
  deleteGroup,
  getAccessCapabilities,
  getAccessContext,
  getAccessOperations,
  getAccessReadiness,
  getGovernance,
  getGroups,
  getHumanRequests,
  getMemberships,
  getPolicy,
  getPolicyRevisions,
  getServices,
  requireVersion,
  retryAccessOperation,
  revokeMembership,
  rollbackPolicy,
  type HumanAction,
  type HumanRequest,
  type Resource,
  type ServiceAccess,
  type ServiceAction,
} from './access-api'
import {
  CreateGroupDialog,
  GovernanceDialog,
  PolicyDialog,
} from './configuration-dialogs'
import {
  HumanActionDialog,
  RequestServiceDialog,
  ServiceActionDialog,
} from './request-dialogs'
import styles from './application-access-page.module.css'

const views = {
  overview: 'Overview',
  governance: 'Governance',
  groups: 'Groups',
  policy: 'Policy',
  humans: 'Human requests',
  memberships: 'Memberships',
  services: 'Service access',
} as const
type View = keyof typeof views
type Versioned = Pick<Resource, 'id' | 'version' | 'state'>
type Editor =
  | 'group'
  | 'governance'
  | 'policy'
  | 'service-request'
  | { kind: 'human'; resource: HumanRequest; action: HumanAction }
  | { kind: 'service'; resource: ServiceAccess; action: ServiceAction }
  | {
      kind: 'confirmation'
      title: string
      description: string
      resource: Versioned
      destructive?: boolean
      reload: () => Promise<Versioned | null>
      submit: (version: number | undefined) => Promise<Versioned>
    }
function pending(rows: { state: string }[] | undefined) {
  return (
    rows?.some((r) =>
      [
        'queued',
        'running',
        'provisioning',
        'activating',
        'revocation-pending',
      ].includes(r.state),
    ) ?? false
  )
}
function QueryMessage({
  query,
  label,
}: {
  query: { isPending: boolean; isError: boolean; error: Error | null }
  label: string
}) {
  if (query.isError)
    return (
      <p role="alert" className={styles.error}>
        {label}: {query.error?.message} Use Refresh to try again.
      </p>
    )
  if (query.isPending)
    return (
      <p role="status" className={styles.mutedSmall}>
        Loading {label.toLowerCase()}…
      </p>
    )
  return null
}
function State({ state }: { state: string }) {
  return <span className={styles.stateBadge}>{state}</span>
}

export function ApplicationAccessPage() {
  const { name } = useParams()
  const { status } = useAuth()
  if (!name) return null
  if (status !== 'authenticated')
    return (
      <section>
        <h1 className={styles.pageTitle}>Application access</h1>
        <p className={styles.marginMedium}>
          Sign in to view this project's application access.
        </p>
      </section>
    )
  return <AccessWorkspace key={name} project={name} />
}

function AccessWorkspace({ project }: { project: string }) {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const requestedView = params.get('view') ?? 'overview'
  const view: View = Object.hasOwn(views, requestedView)
    ? (requestedView as View)
    : 'overview'
  const [editor, setEditor] = React.useState<Editor | null>(null)
  const [deadline, setDeadline] = React.useState(() => Date.now() + 300_000)
  const [timedOut, setTimedOut] = React.useState(false)
  const [writesDenied, setWritesDenied] = React.useState(false)
  const [notice, setNotice] = React.useState<string | null>(null)
  const [showRevokedMemberships, setShowRevokedMemberships] =
    React.useState(false)
  const terminalSeen = React.useRef(new Set<string>())
  const polling = (active: boolean, error: Error | null) =>
    active && (!error || isTransientApiError(error)) && Date.now() < deadline
      ? 2_000
      : false
  const context = useQuery({
    queryKey: accessKeys.resource(project, 'context'),
    queryFn: ({ signal }) => getAccessContext(project, signal),
    refetchOnWindowFocus: true,
  })
  const enabled = Boolean(context.data) && !context.isError
  const capabilities = useQuery({
    queryKey: accessKeys.resource(project, 'capabilities'),
    queryFn: ({ signal }) => getAccessCapabilities(signal),
    enabled,
  })
  const manage =
    enabled &&
    !context.isFetching &&
    !writesDenied &&
    context.data?.permissions.manage === true
  const consume =
    enabled &&
    !context.isFetching &&
    !writesDenied &&
    context.data?.permissions.consume === true
  const adminReads = enabled && context.data?.permissions.manage === true
  const policy = useQuery({
    queryKey: accessKeys.resource(project, 'policy'),
    queryFn: ({ signal }) => getPolicy(project, signal),
    enabled: enabled && context.data?.eligible,
    refetchInterval: (q) =>
      polling(pending(q.state.data ? [q.state.data] : []), q.state.error),
  })
  const groups = useQuery({
    queryKey: accessKeys.resource(project, 'groups'),
    queryFn: ({ signal }) => getGroups(project, signal),
    enabled,
    refetchInterval: (q) => polling(pending(q.state.data), q.state.error),
  })
  const governance = useQuery({
    queryKey: accessKeys.resource(project, 'governance'),
    queryFn: ({ signal }) => getGovernance(project, signal),
    enabled,
  })
  const revisions = useQuery({
    queryKey: accessKeys.resource(project, 'policy-revisions'),
    queryFn: ({ signal }) => getPolicyRevisions(project, signal),
    enabled: enabled && context.data?.eligible && view === 'policy',
  })
  const humans = useQuery({
    queryKey: accessKeys.resource(project, 'humans'),
    queryFn: ({ signal }) => getHumanRequests(project, signal),
    enabled: adminReads,
  })
  const memberships = useQuery({
    queryKey: accessKeys.resource(project, 'memberships'),
    queryFn: ({ signal }) => getMemberships(project, signal),
    enabled: adminReads,
    refetchInterval: (q) => polling(pending(q.state.data), q.state.error),
  })
  const services = useQuery({
    queryKey: accessKeys.resource(project, 'services'),
    queryFn: ({ signal }) => getServices(project, signal),
    enabled,
    refetchInterval: (q) =>
      polling(
        pending(q.state.data) ||
          q.state.data?.some((s) =>
            s.spec.credentials.some(
              (c) =>
                c.state === 'provisioning' || c.state === 'revocation-pending',
            ),
          ) === true,
        q.state.error,
      ),
  })
  const operations = useQuery({
    queryKey: accessKeys.resource(project, 'operations'),
    queryFn: ({ signal }) => getAccessOperations(project, signal),
    enabled,
    refetchInterval: (q) => polling(pending(q.state.data), q.state.error),
  })
  const readiness = useQuery({
    queryKey: accessKeys.resource(project, 'readiness'),
    queryFn: ({ signal }) => getAccessReadiness(project, signal),
    enabled: enabled && context.data?.eligible,
    refetchInterval: (q) =>
      polling(
        q.state.data?.components.some(
          (c) => c.status && c.status.state !== 'ready',
        ) ?? false,
        q.state.error,
      ),
  })

  React.useEffect(() => {
    const timer = window.setTimeout(
      () => setTimedOut(true),
      Math.max(0, deadline - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [deadline])
  React.useEffect(() => {
    const terminals =
      operations.data?.filter(
        (o) => o.state === 'succeeded' || o.state === 'failed',
      ) ?? []
    if (!terminals.some((o) => !terminalSeen.current.has(o.id))) return
    terminals.forEach((o) => terminalSeen.current.add(o.id))
    void client.invalidateQueries({
      queryKey: accessKeys.project(project),
      predicate: (q) => q.queryKey[2] !== 'operations',
    })
    void client.invalidateQueries({
      queryKey: ['projects', project, 'secrets'],
    })
  }, [client, operations.data, project])
  React.useEffect(
    () => () => {
      void client.cancelQueries({ queryKey: accessKeys.project(project) })
      client.removeQueries({ queryKey: accessKeys.project(project) })
    },
    [client, project],
  )

  function closeEditor() {
    setEditor(null)
    window.requestAnimationFrame(() => {
      if (document.activeElement === document.body)
        document.getElementById('application-access-title')?.focus()
    })
  }
  function resume() {
    setDeadline(Date.now() + 300_000)
    setTimedOut(false)
  }
  async function accepted(result: Versioned) {
    resume()
    setNotice(
      `Saved ${result.id}; server state: ${result.state}. Approval and provisioning are separate.`,
    )
    await client.invalidateQueries({ queryKey: accessKeys.project(project) })
  }
  function onDenied() {
    setWritesDenied(true)
    setNotice(
      'The API denied this action. Refresh access context before making further changes.',
    )
    void context.refetch()
  }
  async function refresh() {
    resume()
    const current = await context.refetch()
    if (!current.isError) setWritesDenied(false)
    await client.invalidateQueries({ queryKey: accessKeys.project(project) })
  }
  async function reloadResource<T extends Versioned>(
    load: () => Promise<T[]>,
    id: string,
  ) {
    const row = (await load()).find((r) => r.id === id)
    if (!row) throw new Error('The access resource is no longer available.')
    return row
  }
  const ownPolicy = !policy.isError ? (policy.data ?? null) : null
  const ownGroups = !groups.isError ? (groups.data ?? []) : []
  const ownGovernance = !governance.isError ? (governance.data ?? null) : null
  const policyEditable =
    manage &&
    context.data?.eligible &&
    !policy.isPending &&
    !policy.isError &&
    !groups.isPending &&
    !groups.isError &&
    !governance.isPending &&
    !governance.isError &&
    Boolean(capabilities.data?.modes.length) &&
    (!ownPolicy || ['active', 'failed'].includes(ownPolicy.state))
  const previousRevision = revisions.isSuccess
    ? revisions.data.find((r) => r.id === ownPolicy?.spec.previousRevision)
    : undefined
  const governanceLabels: Record<string, string> = {
    maximumDataClassification: 'Maximum data classification',
    maximumTelemetryClassification: 'Maximum telemetry classification',
    personalData: 'Personal data',
    domainRetentionOwner: 'Domain retention owner',
    domainRetentionPolicy: 'Domain retention policy',
    purgeAuthority: 'Purge authority',
    recoveryOwner: 'Recovery owner',
  }
  const filters = [
    'pending',
    'approved',
    'rejected',
    'cancelled',
    'expired',
    'all',
  ]
  const requestedFilter = params.get('state') ?? 'pending'
  const filter = filters.includes(requestedFilter) ? requestedFilter : 'pending'

  return (
    <AccessEvents.Provider value={{ onDenied }}>
      <section
        className={styles.workspace}
        aria-labelledby="application-access-title"
      >
        <div className={styles.stack}>
          <Link className={styles.smallLink} to={`/projects/${project}`}>
            Back to {project}
          </Link>
          <div className={styles.headerRow}>
            <h1
              tabIndex={-1}
              id="application-access-title"
              className={styles.pageTitle}
            >
              Application access
            </h1>
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={context.isFetching}
            >
              Refresh access
            </Button>
          </div>
          <p className={styles.muted}>
            {project}: configure who can use the hosted application. Project
            roles and CI deployment credentials grant no application membership.
          </p>
        </div>
        <QueryMessage query={context} label="Access context" />
        {context.data && !context.isError && (
          <>
            <nav
              aria-label="Application access sections"
              className={styles.actions}
            >
              {Object.entries(views).map(([key, label]) => (
                <Link
                  key={key}
                  to={`?view=${key}`}
                  aria-current={view === key ? 'page' : undefined}
                  className={`${styles.viewTab} ${view === key ? styles.viewTabActive : ''}`}
                >
                  {label}
                </Link>
              ))}
            </nav>
            {notice && (
              <p role="status" className={styles.notice}>
                {notice}
              </p>
            )}
            {timedOut &&
              (pending(operations.data) ||
                pending(memberships.data) ||
                pending(services.data) ||
                pending(ownPolicy ? [ownPolicy] : [])) && (
                <p role="status">
                  Polling stopped after five minutes. Server operations
                  continue. Refresh access to resume polling.
                </p>
              )}
            {view === 'overview' && (
              <section className={styles.panel} aria-label="Access overview">
                <h2 className={styles.sectionTitle}>Access overview</h2>
                <dl className={styles.detailGrid}>
                  <div>
                    <dt className={styles.muted}>Application</dt>
                    <dd>{context.data.application}</dd>
                  </div>
                  <div>
                    <dt className={styles.muted}>Public component</dt>
                    <dd>{context.data.component ?? 'None'}</dd>
                  </div>
                  <div>
                    <dt className={styles.muted}>Workload readiness</dt>
                    <dd>
                      {readiness.isError
                        ? 'Unavailable'
                        : (readiness.data?.components.find(
                            (c) => c.name === context.data.component,
                          )?.status?.state ?? 'Unknown')}
                    </dd>
                  </div>
                  <div>
                    <dt className={styles.muted}>Access policy</dt>
                    <dd>
                      {!context.data.eligible ? (
                        'Not available'
                      ) : policy.isPending ? (
                        'Loading'
                      ) : policy.isError ? (
                        'Unavailable'
                      ) : ownPolicy ? (
                        <State state={ownPolicy.state} />
                      ) : (
                        'Access not configured; public requests denied'
                      )}
                    </dd>
                  </div>
                </dl>
                {context.data.url && (
                  <p className={styles.smallBreakable}>
                    Public URL:{' '}
                    <a className={styles.link} href={context.data.url}>
                      {context.data.url}
                    </a>
                  </p>
                )}
                {context.data.reason && <p>{context.data.reason}</p>}
                {context.data.eligible && (
                  <>
                    <QueryMessage query={policy} label="Policy" />
                    <QueryMessage
                      query={readiness}
                      label="Workload readiness"
                    />
                  </>
                )}
                <QueryMessage
                  query={capabilities}
                  label="Hosted-access capabilities"
                />
                {capabilities.data && (
                  <p className={styles.small}>
                    Supported authentication:{' '}
                    {capabilities.data.modes.join(', ')}. Maximum authorization
                    staleness:{' '}
                    {capabilities.data.maxAuthorizationStalenessSeconds}{' '}
                    seconds. Credential isolation:{' '}
                    {capabilities.data.credentialIsolation}.
                  </p>
                )}
                {capabilities.isSuccess && !capabilities.data && (
                  <p role="alert">
                    This API does not advertise hosted-application access.
                  </p>
                )}
                <p className={styles.small}>
                  Application-administrator groups protect application routes.
                  They confer no portal administration authority.
                </p>
              </section>
            )}
            {view === 'governance' && (
              <section className={styles.panel}>
                <div className={styles.row}>
                  <h2 className={styles.sectionTitle}>Governance</h2>
                  {manage && !governance.isPending && !governance.isError && (
                    <Button onClick={() => setEditor('governance')}>
                      Edit governance
                    </Button>
                  )}
                </div>
                <QueryMessage query={governance} label="Governance" />
                {governance.isSuccess &&
                  (ownGovernance ? (
                    <dl className={styles.smallStack}>
                      {Object.entries(ownGovernance.spec).map(
                        ([key, value]) => (
                          <div key={key} className={styles.wrappable}>
                            <dt className={styles.strong}>
                              {governanceLabels[key] ?? key}
                            </dt>
                            <dd>{String(value)}</dd>
                          </div>
                        ),
                      )}
                    </dl>
                  ) : (
                    <p>Project governance is not recorded.</p>
                  ))}
              </section>
            )}
            {view === 'groups' && (
              <section className={styles.panel}>
                <div className={styles.row}>
                  <h2 className={styles.sectionTitle}>Groups</h2>
                  {manage && (
                    <Button onClick={() => setEditor('group')}>
                      Create application group
                    </Button>
                  )}
                </div>
                <p className={styles.mutedSmall}>
                  Group creation assigns no members. Names are labels; policy
                  references use stable IDs.
                </p>
                <QueryMessage query={groups} label="Groups" />
                {groups.isSuccess &&
                  (ownGroups.length ? (
                    <ul className={styles.stack}>
                      {ownGroups.map((group) => (
                        <li key={group.id} className={styles.outlinedStack}>
                          <div className={styles.compactRow}>
                            <p>
                              {group.spec.displayName} ({group.name})
                            </p>
                            <State state={group.state} />
                          </div>
                          <p className={styles.mutedTinyBreakable}>
                            {group.id}
                          </p>
                          {manage && group.state === 'active' && (
                            <Button
                              color="red"
                              size="sm"
                              onClick={() =>
                                setEditor({
                                  kind: 'confirmation',
                                  title: 'Delete application group',
                                  description: `Delete ${group.name}? Policies and memberships referencing this group must be removed first.`,
                                  resource: group,
                                  destructive: true,
                                  reload: () =>
                                    reloadResource(
                                      () => getGroups(project),
                                      group.id,
                                    ),
                                  submit: (version) =>
                                    deleteGroup(
                                      project,
                                      group.id,
                                      requireVersion(version),
                                    ),
                                })
                              }
                            >
                              Delete group
                            </Button>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No application groups.</p>
                  ))}
              </section>
            )}
            {view === 'policy' && (
              <section className={styles.panel}>
                <div className={styles.row}>
                  <h2 className={styles.sectionTitle}>Policy</h2>
                  {policyEditable && (
                    <Button onClick={() => setEditor('policy')}>
                      {ownPolicy
                        ? 'Edit access policy'
                        : 'Define access policy'}
                    </Button>
                  )}
                </div>
                {!context.data.eligible ? (
                  <p>{context.data.reason}</p>
                ) : (
                  <>
                    <QueryMessage query={policy} label="Policy" />
                    <QueryMessage query={groups} label="Policy groups" />
                    {policy.isSuccess &&
                      (ownPolicy ? (
                        <>
                          <p>
                            Policy <State state={ownPolicy.state} />; version{' '}
                            {ownPolicy.version}. Saved revisions may still be
                            provisioning.
                          </p>
                          <RouteSummary
                            policy={ownPolicy.spec}
                            groups={ownGroups}
                          />
                          <p className={styles.small}>
                            Identity attributes: display name{' '}
                            {ownPolicy.spec.identityAttributes.displayName
                              ? 'released'
                              : 'off'}
                            ; email{' '}
                            {ownPolicy.spec.identityAttributes.email
                              ? 'released'
                              : 'off'}
                            .
                          </p>
                        </>
                      ) : (
                        <p>Access not configured; public requests denied.</p>
                      ))}
                    <QueryMessage query={revisions} label="Policy revisions" />
                    {revisions.isSuccess && (
                      <ul className={styles.smallStack}>
                        {revisions.data.map((r) => (
                          <li key={r.id} className={styles.breakable}>
                            Revision {r.id}; {r.created_at}
                            {r.id === ownPolicy?.spec.revisionId
                              ? ' (current desired)'
                              : ''}
                          </li>
                        ))}
                      </ul>
                    )}
                    {manage &&
                      previousRevision &&
                      ownPolicy?.spec.previousRevision &&
                      ['active', 'failed'].includes(ownPolicy.state) && (
                        <Button
                          variant="outline"
                          onClick={() =>
                            setEditor({
                              kind: 'confirmation',
                              title: 'Roll back access policy',
                              description:
                                'Apply the previous policy revision. Review its routes below; provisioning can temporarily deny access.',
                              resource: ownPolicy,
                              reload: () => getPolicy(project),
                              submit: (version) =>
                                rollbackPolicy(
                                  project,
                                  requireVersion(version),
                                ),
                            })
                          }
                        >
                          Roll back policy
                        </Button>
                      )}
                  </>
                )}
              </section>
            )}
            {view === 'humans' && (
              <section className={styles.panel}>
                <h2 className={styles.sectionTitle}>Human requests</h2>
                {!adminReads ? (
                  <p>
                    Your platform permissions do not allow human request
                    administration.
                  </p>
                ) : (
                  <>
                    <p className={styles.small}>
                      First login creates a request without membership. Accounts
                      and password recovery are managed by the identity
                      administrator.
                    </p>
                    <label className={styles.blockSmall}>
                      Request state{' '}
                      <select
                        className={styles.inlineSelect}
                        value={filter}
                        onChange={(e) =>
                          setParams({ view: 'humans', state: e.target.value })
                        }
                      >
                        {filters.map((state) => (
                          <option key={state} value={state}>
                            {state}
                          </option>
                        ))}
                      </select>
                    </label>
                    <QueryMessage query={humans} label="Human requests" />
                    {humans.isSuccess && (
                      <RequestRows
                        empty="No requests match this state."
                        rows={humans.data
                          .filter((r) => filter === 'all' || r.state === filter)
                          .map((request) => (
                            <li
                              key={request.id}
                              className={styles.outlinedMediumStack}
                            >
                              <div className={styles.compactRow}>
                                <span className={styles.strongBreakable}>
                                  {request.spec.displayName ??
                                    request.spec.principalId}
                                </span>
                                <State state={request.state} />
                              </div>
                              <p className={styles.tinyBreakable}>
                                {request.id} · created {request.created_at} ·
                                expires {request.spec.expiresAt}
                              </p>
                              <p className={styles.mutedTinyBreakable}>
                                {request.spec.principalId} ·{' '}
                                {request.spec.issuer} / {request.spec.subject}
                              </p>
                              {request.state === 'approved' && (
                                <p className={styles.small}>
                                  Request approved; membership states determine
                                  effective access.
                                </p>
                              )}
                              <div className={styles.actions}>
                                {manage &&
                                  humanActions(request).map((action) => (
                                    <Button
                                      key={action}
                                      size="sm"
                                      variant={
                                        action === 'reject' ||
                                        action === 'cancel'
                                          ? 'destructive'
                                          : 'outline'
                                      }
                                      disabled={
                                        ['approve', 'groups'].includes(
                                          action,
                                        ) &&
                                        (!ownPolicy ||
                                          groups.isError ||
                                          groups.isPending)
                                      }
                                      onClick={() =>
                                        setEditor({
                                          kind: 'human',
                                          resource: request,
                                          action,
                                        })
                                      }
                                    >
                                      {humanButton(action)}
                                    </Button>
                                  ))}
                              </div>
                            </li>
                          ))}
                      />
                    )}
                  </>
                )}
              </section>
            )}
            {view === 'memberships' && (
              <section className={styles.panel}>
                <h2 className={styles.sectionTitle}>Memberships</h2>
                {!adminReads ? (
                  <p>
                    Your platform permissions do not allow membership
                    administration.
                  </p>
                ) : (
                  <>
                    <p className={styles.small}>
                      Only active memberships authorize requests. Revocation
                      takes effect within five minutes; provider cleanup may
                      remain pending.
                    </p>
                    <QueryMessage query={memberships} label="Memberships" />
                    <label className={styles.filter}>
                      <input
                        type="checkbox"
                        checked={showRevokedMemberships}
                        onChange={(event) =>
                          setShowRevokedMemberships(event.target.checked)
                        }
                      />
                      Show revoked memberships
                    </label>
                    {memberships.isSuccess && (
                      <RequestRows
                        empty={
                          memberships.data.length > 0 && !showRevokedMemberships
                            ? 'No memberships match this filter. Select “Show revoked memberships” to view revoked grants.'
                            : 'No application memberships.'
                        }
                        rows={memberships.data
                          .filter(
                            (membership) =>
                              showRevokedMemberships ||
                              membership.state !== 'revoked',
                          )
                          .map((membership) => (
                            <li
                              className={styles.outlinedStack}
                              key={membership.id}
                            >
                              <div className={styles.compactRow}>
                                <span className={styles.breakable}>
                                  {membership.spec.displayName ??
                                    membership.spec.principalId}{' '}
                                  →{' '}
                                  {ownGroups.find(
                                    (g) => g.id === membership.spec.groupId,
                                  )?.name ?? membership.spec.groupId}
                                </span>
                                <State state={membership.state} />
                              </div>
                              <p className={styles.mutedTinyBreakable}>
                                {membership.id} · {membership.spec.principalId}
                              </p>
                              {manage &&
                                ['active', 'provisioning', 'failed'].includes(
                                  membership.state,
                                ) && (
                                  <Button
                                    size="sm"
                                    color="red"
                                    onClick={() =>
                                      setEditor({
                                        kind: 'confirmation',
                                        title: 'Revoke application membership',
                                        description:
                                          'Remove this group grant. Existing sessions and tokens lose this authority within five minutes; cleanup retries independently.',
                                        resource: membership,
                                        destructive: true,
                                        reload: () =>
                                          reloadResource(
                                            () => getMemberships(project),
                                            membership.id,
                                          ),
                                        submit: (version) =>
                                          revokeMembership(
                                            project,
                                            membership.id,
                                            requireVersion(version),
                                          ),
                                      })
                                    }
                                  >
                                    Revoke membership
                                  </Button>
                                )}
                            </li>
                          ))}
                      />
                    )}
                  </>
                )}
              </section>
            )}
            {view === 'services' && (
              <section className={styles.panel}>
                <div className={styles.row}>
                  <h2 className={styles.sectionTitle}>Service access</h2>
                  {consume && (
                    <Button onClick={() => setEditor('service-request')}>
                      Request service access
                    </Button>
                  )}
                </div>
                <QueryMessage query={services} label="Service access" />
                {services.isSuccess && (
                  <>
                    <h3 className={styles.strong}>Incoming service requests</h3>
                    <ServiceRows
                      rows={services.data.filter(
                        (s) => s.spec.providerProject === project,
                      )}
                      project={project}
                      manage={manage}
                      consume={false}
                      onAction={(resource, action) =>
                        setEditor({ kind: 'service', resource, action })
                      }
                      approvalReady={
                        ownPolicy?.state === 'active' &&
                        !groups.isError &&
                        !groups.isPending
                      }
                    />
                    <h3 className={styles.strong}>Outgoing service requests</h3>
                    <ServiceRows
                      rows={services.data.filter((s) => s.project === project)}
                      project={project}
                      manage={false}
                      consume={consume}
                      onAction={(resource, action) =>
                        setEditor({ kind: 'service', resource, action })
                      }
                      approvalReady={false}
                    />
                  </>
                )}
              </section>
            )}
            <section className={styles.panel} aria-label="Access operations">
              <h2 className={styles.sectionTitle}>Access operations</h2>
              <p className={styles.mutedTiny}>
                Latest 100 visible operations. Server work continues if polling
                stops.
              </p>
              <QueryMessage query={operations} label="Access operations" />
              {operations.isSuccess && (
                <RequestRows
                  empty="No access operations."
                  rows={operations.data.map((op) => (
                    <li key={op.id} className={styles.outlinedSmallStack}>
                      <div className={styles.compactRow}>
                        <span>{op.action}</span>
                        <State state={op.state} />
                      </div>
                      <p className={styles.tinyBreakable}>
                        Operation {op.id}; resource {op.resourceId}; attempts{' '}
                        {op.attempts}.
                      </p>
                      {op.errorCode && <p role="alert">{op.errorCode}</p>}
                      {!writesDenied && (manage || consume) && op.canRetry && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setEditor({
                              kind: 'confirmation',
                              title: 'Retry access operation',
                              description: `Retry ${op.action} with your current platform authority.`,
                              resource: {
                                id: op.resourceId,
                                version: op.resourceVersion,
                                state: 'failed',
                              },
                              reload: async () => {
                                const latest = (
                                  await getAccessOperations(project)
                                ).find((r) => r.id === op.id)
                                if (!latest?.canRetry)
                                  throw new Error(
                                    'This operation is no longer retryable. Refresh access.',
                                  )
                                return {
                                  id: latest.resourceId,
                                  version: latest.resourceVersion,
                                  state: latest.state,
                                }
                              },
                              submit: (version) =>
                                retryAccessOperation(
                                  op.id,
                                  requireVersion(version),
                                ),
                            })
                          }
                        >
                          Retry operation
                        </Button>
                      )}
                    </li>
                  ))}
                />
              )}
            </section>
            {editor === 'group' && (
              <CreateGroupDialog
                project={project}
                onAccepted={accepted}
                onClose={closeEditor}
              />
            )}
            {editor === 'governance' && (
              <GovernanceDialog
                project={project}
                resource={ownGovernance}
                onAccepted={accepted}
                onClose={closeEditor}
              />
            )}
            {editor === 'policy' &&
              context.data.component &&
              capabilities.data && (
                <PolicyDialog
                  project={project}
                  component={context.data.component}
                  resource={ownPolicy}
                  groups={ownGroups}
                  personalData={ownGovernance?.spec.personalData ?? false}
                  modes={capabilities.data.modes}
                  onAccepted={accepted}
                  onClose={closeEditor}
                />
              )}
            {editor === 'service-request' && (
              <RequestServiceDialog
                project={project}
                onAccepted={accepted}
                onClose={closeEditor}
              />
            )}
            {typeof editor === 'object' && editor?.kind === 'human' && (
              <HumanActionDialog
                project={project}
                resource={editor.resource}
                action={editor.action}
                groups={ownGroups}
                policy={ownPolicy}
                onAccepted={accepted}
                onClose={closeEditor}
              />
            )}
            {typeof editor === 'object' && editor?.kind === 'service' && (
              <ServiceActionDialog
                project={project}
                resource={editor.resource}
                action={editor.action}
                groups={ownGroups}
                policy={ownPolicy}
                onAccepted={accepted}
                onClose={closeEditor}
              />
            )}
            {typeof editor === 'object' && editor?.kind === 'confirmation' && (
              <AccessDialog
                {...editor}
                submitLabel={editor.title}
                onAccepted={accepted}
                onClose={closeEditor}
              >
                {editor.title === 'Roll back access policy' &&
                  previousRevision && (
                    <RouteSummary
                      policy={previousRevision.spec}
                      groups={ownGroups}
                    />
                  )}
              </AccessDialog>
            )}
          </>
        )}
      </section>
    </AccessEvents.Provider>
  )
}

function RequestRows({
  rows,
  empty,
}: {
  rows: React.ReactNode[]
  empty: string
}) {
  return rows.length ? (
    <ul className={styles.stack}>{rows}</ul>
  ) : (
    <p className={styles.mutedSmall}>{empty}</p>
  )
}
function humanActions(request: HumanRequest): HumanAction[] {
  if (request.state === 'pending')
    return Date.parse(request.spec.expiresAt) > Date.now()
      ? ['approve', 'reject', 'cancel']
      : ['reject', 'cancel']
  if (request.state === 'approved') return ['groups']
  return ['rejected', 'expired', 'cancelled'].includes(request.state)
    ? ['reopen']
    : []
}
function humanButton(action: HumanAction) {
  return {
    approve: 'Approve',
    reject: 'Reject',
    cancel: 'Cancel request',
    reopen: 'Reopen',
    groups: 'Add groups',
  }[action]
}
function ServiceRows({
  rows,
  project,
  manage,
  consume,
  approvalReady,
  onAction,
}: {
  rows: ServiceAccess[]
  project: string
  manage: boolean
  consume: boolean
  approvalReady: boolean
  onAction: (row: ServiceAccess, action: ServiceAction) => void
}) {
  return (
    <RequestRows
      empty="No service requests."
      rows={rows.map((service) => {
        const actions: ServiceAction[] = []
        if (
          manage &&
          service.spec.providerProject === project &&
          service.state === 'pending'
        )
          actions.push('approve', 'reject')
        if (consume && service.project === project) {
          if (service.state === 'pending') actions.push('cancel')
          if (
            service.state === 'active' &&
            !service.spec.credentials.some((c) =>
              ['overlap', 'provisioning', 'revocation-pending'].includes(
                c.state,
              ),
            )
          )
            actions.push('rotate', 'emergency')
          if (
            service.spec.credentials.some((c) => c.state === 'overlap') &&
            service.spec.credentials.some((c) => c.state === 'active')
          )
            actions.push('confirm')
        }
        if (
          (manage || consume) &&
          ['active', 'provisioning', 'failed', 'pending'].includes(
            service.state,
          )
        )
          actions.push('revoke')
        return (
          <li key={service.id} className={styles.outlinedMediumStack}>
            <div className={styles.compactRow}>
              <span className={styles.strong}>{service.name}</span>
              <State state={service.state} />
            </div>
            <p className={styles.small}>
              {service.project} → {service.spec.providerProject}/
              {service.spec.application}
            </p>
            <p className={styles.mutedTinyBreakable}>
              {service.id}; principal {service.spec.principalId}.
            </p>
            <p className={styles.tiny}>
              Every consumer project component can use this credential.
            </p>
            {service.spec.credentials.map((c) => (
              <p className={styles.tinyBreakable} key={c.id}>
                Credential {c.id}: {c.state}
                {c.expiresAt ? `; overlap ends ${c.expiresAt}` : ''}.
              </p>
            ))}
            {service.spec.adoption && (
              <p className={styles.small}>Adoption: {service.spec.adoption}</p>
            )}
            {consume &&
              service.state === 'active' &&
              service.spec.secretPrefix && (
                <div className={styles.noticeStack}>
                  <p className={styles.breakable}>
                    Provider URL: {service.spec.providerUrl}
                  </p>
                  <p className={styles.breakable}>
                    Audience: {service.spec.audience}
                  </p>
                  <p>Managed secret variables:</p>
                  <ul className={styles.breakable}>
                    {['CLIENT_ID', 'CLIENT_SECRET', 'TOKEN_URL'].map(
                      (suffix) => (
                        <li key={suffix}>
                          {service.spec.secretPrefix}_{suffix}
                        </li>
                      ),
                    )}
                  </ul>
                  <p>
                    Obtain a five-minute token using client_credentials. Declare
                    HTTPS egress to the issuer token endpoint and provider host.
                    These credentials grant no Platform API access.
                  </p>
                </div>
              )}
            <div className={styles.actions}>
              {actions.map((action) => (
                <Button
                  size="sm"
                  key={action}
                  variant={
                    ['reject', 'cancel', 'revoke', 'emergency'].includes(action)
                      ? 'destructive'
                      : 'outline'
                  }
                  disabled={action === 'approve' && !approvalReady}
                  onClick={() => onAction(service, action)}
                >
                  {
                    {
                      approve: 'Approve service',
                      reject: 'Reject service',
                      cancel: 'Cancel service',
                      rotate: 'Rotate credential',
                      emergency: 'Emergency rotation',
                      confirm: 'Confirm adoption',
                      revoke: 'Revoke service',
                    }[action]
                  }
                </Button>
              ))}
            </div>
          </li>
        )
      })}
    />
  )
}
