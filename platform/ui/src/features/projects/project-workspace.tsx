import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/auth/auth-context'
import { DeployProjectDialog } from '@/features/projects/deploy-project-dialog'
import { getDataServices, getDeploymentCredentials, getOperation, getProjectConfiguration, getProjectLogs, getProjectRevisions, getProjectSecrets, getResourceInventory, getResourceUsage } from '@/features/projects/projects-api'
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

function memoryMebibytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`
}

function ProjectWorkspace() {
  const { name } = useParams()
  const { status } = useAuth()
  const queryClient = useQueryClient()
  const [operationId, setOperationId] = React.useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [logTail, setLogTail] = React.useState(200)
  const [logSearch, setLogSearch] = React.useState('')
  const [appliedLogSearch, setAppliedLogSearch] = React.useState('')
  const [logAfter, setLogAfter] = React.useState<string | undefined>()
  const revisionsQuery = useQuery({
    queryKey: ['projects', name, 'revisions'],
    queryFn: () => getProjectRevisions(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name),
  })
  const operationQuery = useQuery({
    queryKey: ['operations', operationId],
    queryFn: () => getOperation(operationId ?? ''),
    enabled: status === 'authenticated' && Boolean(operationId),
    refetchInterval: (query) => ['queued', 'running'].includes(query.state.data?.state ?? '') ? 2_000 : false,
  })
  const usageQuery = useQuery({
    queryKey: ['projects', name, 'resource-usage'],
    queryFn: () => getResourceUsage(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined,
    refetchInterval: 15_000,
  })
  const inventoryQuery = useQuery({
    queryKey: ['projects', name, 'resources'], queryFn: () => getResourceInventory(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined,
    refetchInterval: 15_000,
  })
  const logsQuery = useQuery({
    queryKey: ['projects', name, 'logs', logTail, appliedLogSearch, logAfter], queryFn: () => getProjectLogs(name ?? '', logTail, appliedLogSearch, logAfter),
    enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined,
  })
  const configurationQuery = useQuery({ queryKey: ['projects', name, 'configuration'], queryFn: () => getProjectConfiguration(name ?? ''), enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined })
  const secretsQuery = useQuery({ queryKey: ['projects', name, 'secrets'], queryFn: () => getProjectSecrets(name ?? ''), enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined, refetchInterval: 15_000 })
  const dataServicesQuery = useQuery({ queryKey: ['projects', name, 'data-services'], queryFn: () => getDataServices(name ?? ''), enabled: status === 'authenticated' && Boolean(name) })
  const credentialsQuery = useQuery({ queryKey: ['projects', name, 'deployment-credentials'], queryFn: () => getDeploymentCredentials(name ?? ''), enabled: status === 'authenticated' && Boolean(name) })

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
    <section aria-labelledby="project-title" className="max-w-3xl space-y-6">
      <div className="space-y-3">
        <Link className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline" to="/">
          Projects
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 id="project-title" className="text-3xl font-semibold tracking-tight">{name}</h1>
            <p className="mt-1 text-muted-foreground">Desired revision history and deployment context.</p>
          </div>
          <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void refreshProject()} disabled={isRefreshing}>{isRefreshing ? 'Refreshing…' : 'Refresh'}</Button>{revisionsQuery.data?.status === 'retired' ? <PurgeProjectDialog name={name} /> : <RetireProjectDialog name={name} />}</div>
        </div>
      </div>

      {status !== 'authenticated' && <p className="text-sm text-muted-foreground">Sign in to view this project.</p>}
      {revisionsQuery.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading project revisions…</p>}
      {revisionsQuery.isError && <p role="alert" className="text-sm text-destructive">{revisionsQuery.error.message}</p>}
      {operationQuery.data && (
        <section aria-labelledby="operation-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 id="operation-title" className="text-lg font-medium">Deployment operation</h2>
          <p className="mt-2 text-sm text-muted-foreground">Revision {operationQuery.data.revision}: {operationQuery.data.state}; readiness {operationQuery.data.readinessState}{operationQuery.data.readinessReason ? ` (${operationQuery.data.readinessReason})` : ''}.</p>
          {operationQuery.data.errorCode && <p role="alert" className="mt-2 text-sm text-destructive">{operationQuery.data.errorCode}</p>}
        </section>
      )}
      {usageQuery.data && (
        <section aria-labelledby="usage-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 id="usage-title" className="text-lg font-medium">Resource usage</h2>
          <p className="mt-2 text-sm text-muted-foreground">Metrics state: {usageQuery.data.state}{usageQuery.data.reason ? ` (${usageQuery.data.reason})` : ''}.</p>
          {usageQuery.data.totals && (
            <dl className="mt-4 grid grid-cols-2 gap-4 rounded-lg border border-border p-4 text-sm">
              <div><dt className="text-muted-foreground">Total CPU</dt><dd className="mt-1 font-medium">{usageQuery.data.totals.cpuMillicores} mCPU</dd></div>
              <div><dt className="text-muted-foreground">Total memory</dt><dd className="mt-1 font-medium">{memoryMebibytes(usageQuery.data.totals.memoryBytes)}</dd></div>
            </dl>
          )}
          {usageQuery.data.pods.length > 0 && (
            <ul className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">
              {usageQuery.data.pods.map((pod) => <li key={pod.name} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"><span className="font-medium">{pod.name}</span><span className="text-muted-foreground">{pod.cpuMillicores} mCPU · {memoryMebibytes(pod.memoryBytes)}</span></li>)}
            </ul>
          )}
          <p className="mt-1 text-xs text-muted-foreground">Observed {new Date(usageQuery.data.observedAt).toLocaleString()}.</p>
        </section>
      )}
      {usageQuery.isError && <p role="alert" className="text-sm text-destructive">{usageQuery.error.message}</p>}
      {inventoryQuery.data && <section aria-labelledby="inventory-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><h2 id="inventory-title" className="text-lg font-medium">Deployment inventory</h2><p className="mt-2 text-sm text-muted-foreground">Inventory state: {inventoryQuery.data.state}{inventoryQuery.data.reason ? ` (${inventoryQuery.data.reason})` : ''}.</p>{inventoryQuery.data.deployments.map((deployment) => <p key={deployment.name} className="mt-2 text-sm"><span className="font-medium">{deployment.name}</span>: {deployment.readyReplicas ?? 'unknown'}/{deployment.replicas ?? 'unknown'} ready replicas</p>)}</section>}
      {inventoryQuery.isError && <p role="alert" className="text-sm text-destructive">{inventoryQuery.error.message}</p>}
      {logsQuery.data && <section aria-labelledby="logs-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 id="logs-title" className="text-lg font-medium">Recent logs</h2><p className="mt-1 text-sm text-muted-foreground">State: {logsQuery.data.state}{logsQuery.data.reason ? ` (${logsQuery.data.reason})` : ''}.{logsQuery.data.truncated ? ' Output is truncated.' : ''}</p></div><Button variant="outline" onClick={() => void logsQuery.refetch()} disabled={logsQuery.isFetching}>{logsQuery.isFetching ? 'Refreshing…' : 'Refresh'}</Button></div><form className="mt-4 flex gap-2" onSubmit={(event) => { event.preventDefault(); setLogAfter(undefined); setAppliedLogSearch(logSearch) }}><input aria-label="Search logs" className="h-8 flex-1 rounded-lg border border-input bg-transparent px-2.5 text-sm" value={logSearch} maxLength={256} onChange={(event) => setLogSearch(event.target.value)} placeholder="Search logs" /><Button type="submit" variant="outline">Search</Button><select aria-label="Log line limit" className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm" value={logTail} onChange={(event) => setLogTail(Number(event.target.value))}><option value={50}>50 lines</option><option value={200}>200 lines</option><option value={500}>500 lines</option></select></form>{logsQuery.data.lines.length > 0 && <ol className="mt-4 max-h-80 space-y-2 overflow-auto rounded-lg bg-muted p-4 text-xs leading-5">{logsQuery.data.lines.map((line, index) => <li key={`${line.timestamp}-${line.pod}-${index}`}><span className="text-muted-foreground">{line.timestamp} {line.pod}</span><br />{line.message}</li>)}</ol>}{logsQuery.data.nextCursor && <Button className="mt-4" variant="outline" onClick={() => setLogAfter(logsQuery.data?.nextCursor ?? undefined)}>Load newer logs</Button>}</section>}
      {logsQuery.isError && <p role="alert" className="text-sm text-destructive">{logsQuery.error.message}</p>}
      {configurationQuery.data && <section aria-labelledby="configuration-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="configuration-title" className="text-lg font-medium">Configuration</h2><p className="mt-1 text-sm text-muted-foreground">Revision {configurationQuery.data.revision}; activation {configurationQuery.data.activationState}{configurationQuery.data.activationReason ? ` (${configurationQuery.data.activationReason})` : ''}.</p></div><EditConfigurationDialog name={name} revision={configurationQuery.data.revision} values={configurationQuery.data.values} onAccepted={(operation) => setOperationId(operation.operationId)} /></div>{Object.keys(configurationQuery.data.values).length ? <dl className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">{Object.entries(configurationQuery.data.values).map(([key, value]) => <div key={key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-3 px-4 py-3"><dt className="font-medium">{key}</dt><dd className="break-words text-muted-foreground">{value}</dd></div>)}</dl> : <p className="mt-2 text-sm">No configuration values.</p>}</section>}
      {configurationQuery.isError && <p role="alert" className="text-sm text-destructive">{configurationQuery.error.message}</p>}
      {dataServicesQuery.data && <section aria-labelledby="data-services-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><h2 id="data-services-title" className="text-lg font-medium">Data services</h2><RequestRecoveryDialog name={name} /></div>{dataServicesQuery.data.services.map((service) => <p key={`${service.type}-${service.name}`} className="mt-2 text-sm"><span className="font-medium">{service.type} ({service.name})</span>: {service.state}{service.reason ? ` (${service.reason})` : ''}</p>)}{dataServicesQuery.data.latestRecoveryRequest && <p className="mt-3 text-sm text-muted-foreground">Latest recovery request: {dataServicesQuery.data.latestRecoveryRequest.status} ({dataServicesQuery.data.latestRecoveryRequest.reason}), requested {new Date(dataServicesQuery.data.latestRecoveryRequest.requestedAt).toLocaleString()}.</p>}</section>}
      {dataServicesQuery.isError && <p role="alert" className="text-sm text-destructive">{dataServicesQuery.error.message}</p>}
      {credentialsQuery.data && <section aria-labelledby="credentials-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="credentials-title" className="text-lg font-medium">Deployment credentials</h2><p className="mt-1 text-sm text-muted-foreground">Credential metadata only. Secret material is never shown here.</p></div><CreateDeploymentCredentialDialog name={name} /></div>{credentialsQuery.data.credentials.length > 0 ? <ul className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">{credentialsQuery.data.credentials.map((credential) => <li key={credential.id} className="px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-3"><span className="font-medium">{credential.name}</span><div className="flex items-center gap-2"><span className="text-muted-foreground">{credential.status}</span>{credential.status === 'active' && <RotateDeploymentCredentialDialog name={name} credentialId={credential.id} credentialName={credential.name} />}{credential.status !== 'revoked' && <RevokeDeploymentCredentialDialog name={name} credentialId={credential.id} credentialName={credential.name} />}</div></div><p className="mt-1 text-xs text-muted-foreground">Expires {new Date(credential.expiresAt).toLocaleString()}{credential.lastUsedAt ? ` · last used ${new Date(credential.lastUsedAt).toLocaleString()}` : ''}{credential.rotatedFrom ? ' · rotated replacement' : ''}</p></li>)}</ul> : <p className="mt-2 text-sm">No deployment credentials.</p>}</section>}
      {credentialsQuery.isError && <p role="alert" className="text-sm text-destructive">{credentialsQuery.error.message}</p>}
      <ProjectGrants name={name} enabled={status === 'authenticated'} />
      {secretsQuery.data && <section aria-labelledby="secrets-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="secrets-title" className="text-lg font-medium">Secrets</h2><p className="mt-1 text-sm text-muted-foreground">Activation {secretsQuery.data.activationState}{secretsQuery.data.activationReason ? ` (${secretsQuery.data.activationReason})` : ''}. Values are never displayed.</p></div><SetSecretDialog name={name} /></div>{secretsQuery.data.secrets.length > 0 ? <ul className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">{secretsQuery.data.secrets.map((secret) => <li key={secret.name} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"><div><p className="font-medium">{secret.name}</p><p className="text-muted-foreground">Version {secret.version} · {secret.state}</p><div className="mt-2"><SecretActions name={name} secret={secret.name} state={secret.state} activationState={secretsQuery.data.activationState} /></div></div><time className="text-muted-foreground" dateTime={secret.changedAt ?? undefined}>{secret.changedAt ? new Date(secret.changedAt).toLocaleString() : 'Change time unavailable'}</time></li>)}</ul> : <p className="mt-2 text-sm">No secret names configured.</p>}</section>}
      {secretsQuery.isError && <p role="alert" className="text-sm text-destructive">{secretsQuery.error.message}</p>}

      {revisionsQuery.data && (
        <section aria-labelledby="revisions-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 id="revisions-title" className="text-lg font-medium">Revisions</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {revisionsQuery.data.currentRevision === null
                  ? 'This project is empty. Deploy an application to create its first revision.'
                  : `Current desired revision: ${revisionsQuery.data.currentRevision}.`}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {revisionsQuery.data.currentRevision !== null && <RestartProjectDialog name={name} onAccepted={(operation) => setOperationId(operation.operationId)} />}
              <DeployProjectDialog name={name} onAccepted={(operation) => setOperationId(operation.operationId)} />
            </div>
          </div>
          {revisionsQuery.data.revisions.length > 0 && (
            <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
              {revisionsQuery.data.revisions.map((revision) => (
                <li key={revision.revision} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <p className="font-medium">Revision {revision.revision}</p>
                    <p className="text-sm text-muted-foreground">{revision.image ?? 'Image unavailable'}</p>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    {revision.current && <Badge variant="secondary">Current</Badge>}
                    {!revision.current && revisionsQuery.data.currentRevision !== null && <RollbackProjectDialog name={name} targetRevision={revision.revision} currentRevision={revisionsQuery.data.currentRevision} onAccepted={(operation) => setOperationId(operation.operationId)} />}
                    <time dateTime={revision.createdAt}>{new Date(revision.createdAt).toLocaleString()}</time>
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
