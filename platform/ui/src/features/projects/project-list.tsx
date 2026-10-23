import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { useAuth } from '@/auth/auth-context'
import { CreateProjectDialog } from '@/features/projects/create-project-dialog'
import { listProjects } from '@/features/projects/projects-api'

function ProjectList() {
  const { status } = useAuth()
  const [showRetired, setShowRetired] = useState(false)
  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
    enabled: status === 'authenticated',
  })
  const visibleProjects = projectsQuery.data?.filter(
    (project) => showRetired || project.status !== 'retired',
  )

  if (status !== 'authenticated') {
    return null
  }

  return (
    <section
      aria-labelledby="projects-title"
      className="rounded-xl border border-border bg-card p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="projects-title" className="text-lg font-medium">
            Projects
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Projects returned by your current platform grants.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <CreateProjectDialog />
          <Button
            variant="outline"
            onClick={() => void projectsQuery.refetch()}
            disabled={projectsQuery.isFetching}
          >
            {projectsQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={showRetired}
          onChange={(event) => setShowRetired(event.target.checked)}
        />
        Show retired projects
      </label>

      {projectsQuery.isLoading && (
        <p role="status" className="mt-4 text-sm text-muted-foreground">
          Loading projects…
        </p>
      )}

      {projectsQuery.isError && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {projectsQuery.error.message}
        </p>
      )}

      {projectsQuery.data?.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">
          You do not currently have access to any projects.
        </p>
      )}

      {projectsQuery.data &&
        projectsQuery.data.length > 0 &&
        visibleProjects?.length === 0 && (
          <p className="mt-4 text-sm text-muted-foreground">
            All your projects are retired. Select “Show retired projects” to
            view them.
          </p>
        )}

      {visibleProjects && visibleProjects.length > 0 && (
        <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
          {visibleProjects.map((project) => (
            <li
              key={project.name}
              className="flex items-center justify-between gap-4 px-4 py-3"
            >
              <Link
                className="font-medium underline-offset-4 hover:underline"
                to={`/projects/${project.name}`}
              >
                {project.name}
              </Link>
              <span className="text-sm text-muted-foreground">
                {project.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export { ProjectList }
