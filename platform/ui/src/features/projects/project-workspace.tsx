import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/auth/auth-context'
import { DeployProjectDialog } from '@/features/projects/deploy-project-dialog'
import { getProjectRevisions } from '@/features/projects/projects-api'

function ProjectWorkspace() {
  const { name } = useParams()
  const { status } = useAuth()
  const revisionsQuery = useQuery({
    queryKey: ['projects', name, 'revisions'],
    queryFn: () => getProjectRevisions(name ?? ''),
    enabled: status === 'authenticated' && Boolean(name),
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
            <DeployProjectDialog name={name} />
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
