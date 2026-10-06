import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/auth/auth-context'
import { DeployProjectDialog } from '@/features/projects/deploy-project-dialog'
import { getOperation, getProjectLogs, getProjectRevisions, getResourceInventory, getResourceUsage } from '@/features/projects/projects-api'

function memoryMebibytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`
}

function ProjectWorkspace() {
  const { name } = useParams()
  const { status } = useAuth()
  const [operationId, setOperationId] = React.useState<string | null>(null)
  const [logTail, setLogTail] = React.useState(200)
  const [logSearch, setLogSearch] = React.useState('')
  const [appliedLogSearch, setAppliedLogSearch] = React.useState('')
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
    queryKey: ['projects', name, 'logs', logTail, appliedLogSearch], queryFn: () => getProjectLogs(name ?? '', logTail, appliedLogSearch),
    enabled: status === 'authenticated' && Boolean(name) && revisionsQuery.data?.currentRevision !== null && revisionsQuery.data !== undefined,
  })

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
          <Button variant="outline" onClick={() => void revisionsQuery.refetch()} disabled={revisionsQuery.isFetching}>
            {revisionsQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
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
      {logsQuery.data && <section aria-labelledby="logs-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 id="logs-title" className="text-lg font-medium">Recent logs</h2><p className="mt-1 text-sm text-muted-foreground">State: {logsQuery.data.state}{logsQuery.data.reason ? ` (${logsQuery.data.reason})` : ''}.{logsQuery.data.truncated ? ' Output is truncated.' : ''}</p></div><Button variant="outline" onClick={() => void logsQuery.refetch()} disabled={logsQuery.isFetching}>{logsQuery.isFetching ? 'Refreshing…' : 'Refresh'}</Button></div><form className="mt-4 flex gap-2" onSubmit={(event) => { event.preventDefault(); setAppliedLogSearch(logSearch) }}><input aria-label="Search logs" className="h-8 flex-1 rounded-lg border border-input bg-transparent px-2.5 text-sm" value={logSearch} maxLength={256} onChange={(event) => setLogSearch(event.target.value)} placeholder="Search logs" /><Button type="submit" variant="outline">Search</Button><select aria-label="Log line limit" className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm" value={logTail} onChange={(event) => setLogTail(Number(event.target.value))}><option value={50}>50 lines</option><option value={200}>200 lines</option><option value={500}>500 lines</option></select></form>{logsQuery.data.lines.length > 0 && <ol className="mt-4 max-h-80 space-y-2 overflow-auto rounded-lg bg-muted p-4 text-xs leading-5">{logsQuery.data.lines.map((line, index) => <li key={`${line.timestamp}-${line.pod}-${index}`}><span className="text-muted-foreground">{line.timestamp} {line.pod}</span><br />{line.message}</li>)}</ol>}</section>}
      {logsQuery.isError && <p role="alert" className="text-sm text-destructive">{logsQuery.error.message}</p>}

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
            <DeployProjectDialog name={name} onAccepted={(operation) => setOperationId(operation.operationId)} />
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
