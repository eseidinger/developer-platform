import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { Badge } from '@mantine/core'
import { Button } from '@mantine/core'
import styles from './project-workspace.module.css'
import { useAuth } from '@/auth/auth-context'
import { DeployProjectDialog } from '@/features/projects/deploy-project-dialog'
import {
  getDataServices,
  getDeploymentCredentials,
  getOperation,
  getProjectConfiguration,
  getProjectLogs,
  getProjectRevisions,
  getProjectSecrets,
  getResourceInventory,
  getResourceUsage,
  listProjects,
} from '@/features/projects/projects-api'
import { SecretActions } from '@/features/projects/secret-rotation-actions'
import { SetSecretDialog } from '@/features/projects/set-secret-dialog'
import { RollbackProjectDialog } from '@/features/projects/rollback-project-dialog'
import { RestartProjectDialog } from '@/features/projects/restart-project-dialog'
import { EditConfigurationDialog } from '@/features/projects/edit-configuration-dialog'
import { RetireProjectDialog } from '@/features/projects/retire-project-dialog'
import { PurgeProjectDialog } from '@/features/projects/purge-project-dialog'
import { RequestRecoveryDialog } from '@/features/projects/request-recovery-dialog'
import { CreateDeploymentCredentialDialog } from '@/features/projects/create-deployment-credential-dialog'
import { RevokeDeploymentCredentialDialog } from '@/features/projects/revoke-deployment-credential-dialog'
import { RotateDeploymentCredentialDialog } from '@/features/projects/rotate-deployment-credential-dialog'
import { ProjectGrants } from '@/features/projects/project-grants'
import { ProjectNavigation } from '@/features/projects/project-navigation'

function memoryMebibytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`
}

function ProjectWorkspace() {
  const { name } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { status } = useAuth()
  const queryClient = useQueryClient()
  const [operationId, setOperationId] = React.useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [logSearch, setLogSearch] = React.useState(
    searchParams.get('log-search') ?? '',
  )
  const appliedLogSearch = searchParams.get('log-search') ?? ''
  const logTail = Number(searchParams.get('log-tail') ?? '200')
  const logComponent = searchParams.get('log-component') ?? ''
  const logInstance = searchParams.get('log-instance') ?? ''
  const logSinceSeconds = Number(searchParams.get('log-since') ?? '0')
  const logAfter = searchParams.get('log-after') ?? undefined

  function setLogFilters(next: Record<string, string | undefined>) {
    const updated = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(next)) {
      if (value) updated.set(key, value)
      else updated.delete(key)
    }
    setSearchParams(updated, { replace: true })
  }
  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
    enabled: status === 'authenticated',
  })
  const projectStatus = projectsQuery.data?.find(
    (project) => project.name === name,
  )?.status
  const statusColor =
    projectStatus === 'retired'
      ? 'gray'
      : projectStatus === 'failed'
        ? 'red'
        : projectStatus === 'active' || projectStatus === 'applied'
          ? 'teal'
          : 'indigo'
  const revisionsQuery = useQuery({
    queryKey: ['projects', name, 'revisions'],
    queryFn: () => getProjectRevisions(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name),
  })
  const operationQuery = useQuery({
    queryKey: ['operations', operationId],
    queryFn: () => getOperation(operationId ?? ''),
    enabled: status === 'authenticated' && Boolean(operationId),
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.state ?? '')
        ? 2_000
        : false,
  })
  const usageQuery = useQuery({
    queryKey: ['projects', name, 'resource-usage'],
    queryFn: () => getResourceUsage(name ?? ''),
    enabled:
      status === 'authenticated' &&
      Boolean(name) &&
      revisionsQuery.data?.currentRevision !== null &&
      revisionsQuery.data !== undefined,
    refetchInterval: 15_000,
  })
  const inventoryQuery = useQuery({
    queryKey: ['projects', name, 'resources'],
    queryFn: () => getResourceInventory(name ?? ''),
    enabled:
      status === 'authenticated' &&
      Boolean(name) &&
      revisionsQuery.data?.currentRevision !== null &&
      revisionsQuery.data !== undefined,
    refetchInterval: 15_000,
  })
  const logsQuery = useQuery({
    queryKey: [
      'projects',
      name,
      'logs',
      logTail,
      appliedLogSearch,
      logComponent,
      logInstance,
      logSinceSeconds,
      logAfter,
    ],
    queryFn: () =>
      getProjectLogs(name ?? '', {
        tail: logTail,
        search: appliedLogSearch,
        component: logComponent,
        instance: logInstance,
        sinceSeconds: logSinceSeconds || undefined,
        after: logAfter,
      }),
    enabled:
      status === 'authenticated' &&
      Boolean(name) &&
      revisionsQuery.data?.currentRevision !== null &&
      revisionsQuery.data !== undefined,
  })
  const configurationQuery = useQuery({
    queryKey: ['projects', name, 'configuration'],
    queryFn: () => getProjectConfiguration(name ?? ''),
    enabled:
      status === 'authenticated' &&
      Boolean(name) &&
      revisionsQuery.data?.currentRevision !== null &&
      revisionsQuery.data !== undefined,
  })
  const secretsQuery = useQuery({
    queryKey: ['projects', name, 'secrets'],
    queryFn: () => getProjectSecrets(name ?? ''),
    enabled:
      status === 'authenticated' &&
      Boolean(name) &&
      revisionsQuery.data?.currentRevision !== null &&
      revisionsQuery.data !== undefined,
    refetchInterval: 15_000,
  })
  const dataServicesQuery = useQuery({
    queryKey: ['projects', name, 'data-services'],
    queryFn: () => getDataServices(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name),
  })
  const credentialsQuery = useQuery({
    queryKey: ['projects', name, 'deployment-credentials'],
    queryFn: () => getDeploymentCredentials(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name),
  })

  async function refreshProject() {
    setIsRefreshing(true)
    try {
      await queryClient.invalidateQueries({ queryKey: ['projects', name] })
    } finally {
      setIsRefreshing(false)
    }
  }

  if (!name) {
    return null
  }

  return (
    <section aria-labelledby="project-title" className={styles.workspace}>
      <div className={styles.stack}>
        <Link className={styles.mutedLink} to="/">
          Projects
        </Link>
        <div className={styles.headerRow}>
          <div>
            <div className={styles.titleLine}>
              <h1 id="project-title" className={styles.pageTitle}>
                {name}
              </h1>
              {projectStatus && (
                <Badge color={statusColor} variant="light" size="lg">
                  {projectStatus}
                </Badge>
              )}
            </div>
            <p className={styles.mutedBelow}>
              Desired revision history and deployment context.
            </p>
          </div>
          <div className={styles.actions}>
            {revisionsQuery.data && (
              <DeployProjectDialog
                name={name}
                onAccepted={(operation) =>
                  setOperationId(operation.operationId)
                }
              />
            )}
            <Button
              variant="subtle"
              onClick={() => void refreshProject()}
              disabled={isRefreshing}
            >
              {isRefreshing ? 'Refreshing…' : 'Refresh'}
            </Button>
            {projectStatus === 'retired' ? (
              <PurgeProjectDialog name={name} />
            ) : (
              <RetireProjectDialog name={name} />
            )}
          </div>
        </div>
        <ProjectNavigation name={name} />
      </div>

      {status !== 'authenticated' && (
        <p className={styles.mutedSmall}>Sign in to view this project.</p>
      )}
      {revisionsQuery.isLoading && (
        <p role="status" className={styles.mutedSmall}>
          Loading project revisions…
        </p>
      )}
      {revisionsQuery.isError && (
        <p role="alert" className={styles.error}>
          {revisionsQuery.error.message}
        </p>
      )}
      {operationQuery.data && (
        <section aria-labelledby="operation-title" className={styles.panel}>
          <h2 id="operation-title" className={styles.sectionTitle}>
            Deployment operation
          </h2>
          <p className={styles.mutedSmallBelowMedium}>
            Revision {operationQuery.data.revision}: {operationQuery.data.state}
            ; readiness {operationQuery.data.readinessState}
            {operationQuery.data.readinessReason
              ? ` (${operationQuery.data.readinessReason})`
              : ''}
            .
          </p>
          {operationQuery.data.errorCode && (
            <p role="alert" className={styles.errorBelow}>
              {operationQuery.data.errorCode}
            </p>
          )}
        </section>
      )}
      {usageQuery.data && (
        <section aria-labelledby="usage-title" className={styles.panel}>
          <h2 id="usage-title" className={styles.sectionTitle}>
            Resource usage
          </h2>
          <p className={styles.mutedSmallBelowMedium}>
            Metrics state: {usageQuery.data.state}
            {usageQuery.data.reason ? ` (${usageQuery.data.reason})` : ''}.
          </p>
          {usageQuery.data.totals && (
            <dl className={styles.detailPanel}>
              <div>
                <dt className={styles.muted}>Total CPU</dt>
                <dd className={styles.itemTitle}>
                  {usageQuery.data.totals.cpuMillicores} mCPU
                </dd>
              </div>
              <div>
                <dt className={styles.muted}>Total memory</dt>
                <dd className={styles.itemTitle}>
                  {memoryMebibytes(usageQuery.data.totals.memoryBytes)}
                </dd>
              </div>
            </dl>
          )}
          {usageQuery.data.pods.length > 0 && (
            <ul className={styles.smallList}>
              {usageQuery.data.pods.map((pod) => (
                <li key={pod.name} className={styles.listRow}>
                  <span className={styles.strong}>{pod.name}</span>
                  <span className={styles.muted}>
                    {pod.cpuMillicores} mCPU ·{' '}
                    {memoryMebibytes(pod.memoryBytes)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className={styles.mutedTinyBelow}>
            Observed {new Date(usageQuery.data.observedAt).toLocaleString()}.
          </p>
        </section>
      )}
      {usageQuery.isError && (
        <p role="alert" className={styles.error}>
          {usageQuery.error.message}
        </p>
      )}
      {inventoryQuery.data && (
        <section aria-labelledby="inventory-title" className={styles.panel}>
          <h2 id="inventory-title" className={styles.sectionTitle}>
            Deployment inventory
          </h2>
          <p className={styles.mutedSmallBelowMedium}>
            Inventory state: {inventoryQuery.data.state}
            {inventoryQuery.data.reason
              ? ` (${inventoryQuery.data.reason})`
              : ''}
            .
          </p>
          {inventoryQuery.data.deployments.map((deployment) => (
            <p key={deployment.name} className={styles.smallBelow}>
              <span className={styles.strong}>{deployment.name}</span>:{' '}
              {deployment.readyReplicas ?? 'unknown'}/
              {deployment.replicas ?? 'unknown'} ready replicas
            </p>
          ))}
        </section>
      )}
      {inventoryQuery.isError && (
        <p role="alert" className={styles.error}>
          {inventoryQuery.error.message}
        </p>
      )}
      {logsQuery.data && (
        <section aria-labelledby="logs-title" className={styles.panel}>
          <div className={styles.compactHeader}>
            <div>
              <h2 id="logs-title" className={styles.sectionTitle}>
                Recent logs
              </h2>
              <p className={styles.mutedSmallBelow}>
                State: {logsQuery.data.state}
                {logsQuery.data.reason ? ` (${logsQuery.data.reason})` : ''}.
                {logsQuery.data.truncated ? ' Output is truncated.' : ''}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => void logsQuery.refetch()}
              disabled={logsQuery.isFetching}
            >
              {logsQuery.isFetching ? 'Refreshing…' : 'Refresh'}
            </Button>
          </div>
          <form
            className={styles.summaryGrid}
            onSubmit={(event) => {
              event.preventDefault()
              setLogFilters({ 'log-search': logSearch, 'log-after': undefined })
            }}
          >
            <input
              aria-label="Search logs"
              className={styles.field}
              value={logSearch}
              maxLength={256}
              onChange={(event) => setLogSearch(event.target.value)}
              placeholder="Search logs"
            />
            <input
              aria-label="Log component"
              className={styles.field}
              value={logComponent}
              maxLength={32}
              onChange={(event) =>
                setLogFilters({
                  'log-component': event.target.value,
                  'log-after': undefined,
                })
              }
              placeholder="Component"
            />
            <input
              aria-label="Log instance"
              className={styles.field}
              value={logInstance}
              maxLength={253}
              onChange={(event) =>
                setLogFilters({
                  'log-instance': event.target.value,
                  'log-after': undefined,
                })
              }
              placeholder="Pod instance"
            />
            <select
              aria-label="Log time range"
              className={styles.compactField}
              value={logSinceSeconds}
              onChange={(event) =>
                setLogFilters({
                  'log-since':
                    event.target.value === '0' ? undefined : event.target.value,
                  'log-after': undefined,
                })
              }
            >
              <option value={0}>Available logs</option>
              <option value={3600}>Last hour</option>
              <option value={21600}>Last 6 hours</option>
              <option value={86400}>Last 24 hours</option>
            </select>
            <select
              aria-label="Log line limit"
              className={styles.compactField}
              value={logTail}
              onChange={(event) =>
                setLogFilters({
                  'log-tail': event.target.value,
                  'log-after': undefined,
                })
              }
            >
              <option value={50}>50 lines</option>
              <option value={200}>200 lines</option>
              <option value={500}>500 lines</option>
            </select>
            <Button type="submit" variant="outline">
              Apply log filters
            </Button>
          </form>
          {logsQuery.data.lines.length > 0 && (
            <ol className={styles.logPanel}>
              {logsQuery.data.lines.map((line, index) => (
                <li key={`${line.timestamp}-${line.pod}-${index}`}>
                  <span className={styles.muted}>
                    {line.timestamp} {line.pod}
                  </span>
                  <br />
                  {line.message}
                </li>
              ))}
            </ol>
          )}
          {logsQuery.data.nextCursor && (
            <Button
              className={styles.marginLarge}
              variant="outline"
              onClick={() =>
                setLogFilters({
                  'log-after': logsQuery.data?.nextCursor ?? undefined,
                })
              }
            >
              Load newer logs
            </Button>
          )}
        </section>
      )}
      {logsQuery.isError && (
        <p role="alert" className={styles.error}>
          {logsQuery.error.message}
        </p>
      )}
      {configurationQuery.data && (
        <section aria-labelledby="configuration-title" className={styles.panel}>
          <div className={styles.headerRow}>
            <div>
              <h2 id="configuration-title" className={styles.sectionTitle}>
                Configuration
              </h2>
              <p className={styles.mutedSmallBelow}>
                Revision {configurationQuery.data.revision}; activation{' '}
                {configurationQuery.data.activationState}
                {configurationQuery.data.activationReason
                  ? ` (${configurationQuery.data.activationReason})`
                  : ''}
                .
              </p>
            </div>
            <EditConfigurationDialog
              name={name}
              revision={configurationQuery.data.revision}
              values={configurationQuery.data.values}
              onAccepted={(operation) => setOperationId(operation.operationId)}
            />
          </div>
          {Object.keys(configurationQuery.data.values).length ? (
            <dl className={styles.smallList}>
              {Object.entries(configurationQuery.data.values).map(
                ([key, value]) => (
                  <div key={key} className={styles.keyValueRow}>
                    <dt className={styles.strong}>{key}</dt>
                    <dd className={styles.mutedWrap}>{value}</dd>
                  </div>
                ),
              )}
            </dl>
          ) : (
            <p className={styles.smallBelow}>No configuration values.</p>
          )}
        </section>
      )}
      {configurationQuery.isError && (
        <p role="alert" className={styles.error}>
          {configurationQuery.error.message}
        </p>
      )}
      {dataServicesQuery.data && (
        <section aria-labelledby="data-services-title" className={styles.panel}>
          <div className={styles.headerRow}>
            <h2 id="data-services-title" className={styles.sectionTitle}>
              Data services
            </h2>
            <RequestRecoveryDialog name={name} />
          </div>
          {dataServicesQuery.data.services.length === 0 && (
            <p className={styles.smallBelow}>No named data resources.</p>
          )}
          {dataServicesQuery.data.services.map((service) => (
            <p key={service.resourceId} className={styles.smallBelow}>
              <span className={styles.strong}>
                {service.type} ({service.name})
              </span>
              : {service.state}
              {service.ownerProject !== name
                ? ` · owned by ${service.ownerProject}`
                : ''}
              {service.reason ? ` (${service.reason})` : ''}
            </p>
          ))}
          {dataServicesQuery.data.bindings.map((binding) => (
            <p key={binding.bindingId} className={styles.smallBelow}>
              {binding.component} binding: {binding.state} /{' '}
              {binding.observedState} · credential{' '}
              {binding.credentialActive ? 'active' : 'not active'}
              {binding.reason ? ` (${binding.reason})` : ''}
            </p>
          ))}
          {dataServicesQuery.data.latestRecoveryRequest && (
            <p className={styles.mutedSmallBelowLarge}>
              Latest recovery request:{' '}
              {dataServicesQuery.data.latestRecoveryRequest.status} (
              {dataServicesQuery.data.latestRecoveryRequest.reason}), requested{' '}
              {new Date(
                dataServicesQuery.data.latestRecoveryRequest.requestedAt,
              ).toLocaleString()}
              .
            </p>
          )}
        </section>
      )}
      {dataServicesQuery.isError && (
        <p role="alert" className={styles.error}>
          {dataServicesQuery.error.message}
        </p>
      )}

      {credentialsQuery.data && (
        <section aria-labelledby="credentials-title" className={styles.panel}>
          <div className={styles.headerRow}>
            <div>
              <h2 id="credentials-title" className={styles.sectionTitle}>
                Deployment credentials
              </h2>
              <p className={styles.mutedSmallBelow}>
                Credential metadata only. Secret material is never shown here.
              </p>
            </div>
            <CreateDeploymentCredentialDialog name={name} />
          </div>
          {credentialsQuery.data.credentials.length > 0 ? (
            <ul className={styles.smallList}>
              {credentialsQuery.data.credentials.map((credential) => (
                <li key={credential.id} className={styles.listCell}>
                  <div className={styles.headerRow}>
                    <span className={styles.strong}>{credential.name}</span>
                    <div className={styles.inlineGroup}>
                      <span className={styles.muted}>{credential.status}</span>
                      {credential.status === 'active' && (
                        <RotateDeploymentCredentialDialog
                          name={name}
                          credentialId={credential.id}
                          credentialName={credential.name}
                        />
                      )}
                      {credential.status !== 'revoked' && (
                        <RevokeDeploymentCredentialDialog
                          name={name}
                          credentialId={credential.id}
                          credentialName={credential.name}
                        />
                      )}
                    </div>
                  </div>
                  <p className={styles.mutedTinyBelow}>
                    Expires {new Date(credential.expiresAt).toLocaleString()}
                    {credential.lastUsedAt
                      ? ` · last used ${new Date(credential.lastUsedAt).toLocaleString()}`
                      : ''}
                    {credential.rotatedFrom ? ' · rotated replacement' : ''}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.smallBelow}>No deployment credentials.</p>
          )}
        </section>
      )}
      {credentialsQuery.isError && (
        <p role="alert" className={styles.error}>
          {credentialsQuery.error.message}
        </p>
      )}
      <ProjectGrants name={name} enabled={status === 'authenticated'} />
      {secretsQuery.data && (
        <section aria-labelledby="secrets-title" className={styles.panel}>
          <div className={styles.headerRow}>
            <div>
              <h2 id="secrets-title" className={styles.sectionTitle}>
                Secrets
              </h2>
              <p className={styles.mutedSmallBelow}>
                Activation {secretsQuery.data.activationState}
                {secretsQuery.data.activationReason
                  ? ` (${secretsQuery.data.activationReason})`
                  : ''}
                . Values are never displayed.
              </p>
            </div>
            <SetSecretDialog name={name} />
          </div>
          {secretsQuery.data.secrets.length > 0 ? (
            <ul className={styles.smallList}>
              {secretsQuery.data.secrets.map((secret) => (
                <li key={secret.name} className={styles.listRow}>
                  <div>
                    <p className={styles.strong}>{secret.name}</p>
                    <p className={styles.muted}>
                      Version {secret.version} · {secret.state}
                    </p>
                    <div className={styles.marginSmall}>
                      <SecretActions
                        name={name}
                        secret={secret.name}
                        state={secret.state}
                        activationState={secretsQuery.data.activationState}
                      />
                    </div>
                  </div>
                  <time
                    className={styles.muted}
                    dateTime={secret.changedAt ?? undefined}
                  >
                    {secret.changedAt
                      ? new Date(secret.changedAt).toLocaleString()
                      : 'Change time unavailable'}
                  </time>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.smallBelow}>No secret names configured.</p>
          )}
        </section>
      )}
      {secretsQuery.isError && (
        <p role="alert" className={styles.error}>
          {secretsQuery.error.message}
        </p>
      )}

      {revisionsQuery.data && (
        <section aria-labelledby="revisions-title" className={styles.panel}>
          <div className={styles.headerRow}>
            <div>
              <h2 id="revisions-title" className={styles.sectionTitle}>
                Revisions
              </h2>
              <p className={styles.mutedSmallBelow}>
                {revisionsQuery.data.currentRevision === null
                  ? 'This project is empty. Deploy an application to create its first revision.'
                  : `Current desired revision: ${revisionsQuery.data.currentRevision}.`}
              </p>
            </div>
            <div className={styles.actions}>
              {revisionsQuery.data.currentRevision !== null && (
                <RestartProjectDialog
                  name={name}
                  onAccepted={(operation) =>
                    setOperationId(operation.operationId)
                  }
                />
              )}
            </div>
          </div>
          {revisionsQuery.data.revisions.length > 0 && (
            <ul className={styles.list}>
              {revisionsQuery.data.revisions.map((revision) => (
                <li key={revision.revision} className={styles.listRow}>
                  <div>
                    <p className={styles.strong}>
                      Revision {revision.revision}
                    </p>
                    <p className={styles.mutedSmall}>
                      {revision.image ?? 'Image unavailable'}
                    </p>
                  </div>
                  <div className={styles.mutedGroup}>
                    {revision.current && (
                      <Badge variant="light" color="gray">
                        Current
                      </Badge>
                    )}
                    {!revision.current &&
                      revisionsQuery.data.currentRevision !== null && (
                        <RollbackProjectDialog
                          name={name}
                          targetRevision={revision.revision}
                          currentRevision={revisionsQuery.data.currentRevision}
                          onAccepted={(operation) =>
                            setOperationId(operation.operationId)
                          }
                        />
                      )}
                    <time dateTime={revision.createdAt}>
                      {new Date(revision.createdAt).toLocaleString()}
                    </time>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </section>
  )
}

export { ProjectWorkspace }
