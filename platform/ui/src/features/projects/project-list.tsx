import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert, Badge, Button, Checkbox, Paper, Skeleton } from '@mantine/core'
import { useAuth } from '@/auth/auth-context'
import { CreateProjectDialog } from '@/features/projects/create-project-dialog'
import { listProjects } from '@/features/projects/projects-api'
import styles from './project-list.module.css'

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

  function statusColor(projectStatus: string) {
    if (projectStatus === 'retired') return 'gray'
    if (projectStatus === 'failed') return 'red'
    if (projectStatus === 'active' || projectStatus === 'applied') return 'teal'
    return 'indigo'
  }

  if (status !== 'authenticated') {
    return null
  }

  return (
    <section aria-labelledby="projects-title" className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h2 id="projects-title" className={styles.heading}>
            Projects
          </h2>
          <p className={styles.intro}>
            Projects available through your current platform grants.
          </p>
        </div>
        <div className={styles.actions}>
          <CreateProjectDialog />
          <Button
            variant="subtle"
            onClick={() => void projectsQuery.refetch()}
            disabled={projectsQuery.isFetching}
          >
            {projectsQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      <Checkbox
        className={styles.filter}
        checked={showRetired}
        onChange={(event) => setShowRetired(event.target.checked)}
        label="Show retired projects"
      />

      {projectsQuery.isLoading && (
        <div role="status" className={styles.loading}>
          <p className={styles.message}>Loading projects…</p>
          <Skeleton height={76} radius="md" />
          <Skeleton height={76} radius="md" />
        </div>
      )}

      {projectsQuery.isError && (
        <Alert color="red" title="Projects unavailable" role="alert">
          {projectsQuery.error.message}
        </Alert>
      )}

      {projectsQuery.data?.length === 0 && (
        <p className={styles.empty}>
          You do not currently have access to any projects.
        </p>
      )}

      {projectsQuery.data &&
        projectsQuery.data.length > 0 &&
        visibleProjects?.length === 0 && (
          <p className={styles.empty}>
            All your projects are retired. Select “Show retired projects” to
            view them.
          </p>
        )}

      {visibleProjects && visibleProjects.length > 0 && (
        <ul className={styles.list}>
          {visibleProjects.map((project) => (
            <Paper
              component="li"
              withBorder
              radius="lg"
              key={project.name}
              className={styles.listItem}
            >
              <Link
                className={styles.projectLink}
                to={`/projects/${project.name}`}
              >
                {project.name}
              </Link>
              <Badge color={statusColor(project.status)} variant="light">
                {project.status}
              </Badge>
            </Paper>
          ))}
        </ul>
      )}
    </section>
  )
}

export { ProjectList }
