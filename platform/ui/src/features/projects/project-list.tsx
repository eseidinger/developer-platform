import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@mantine/core'
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
            Projects returned by your current platform grants.
          </p>
        </div>
        <div className={styles.actions}>
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

      <label className={styles.filter}>
        <input
          type="checkbox"
          checked={showRetired}
          onChange={(event) => setShowRetired(event.target.checked)}
        />
        Show retired projects
      </label>

      {projectsQuery.isLoading && (
        <p role="status" className={styles.message}>
          Loading projects…
        </p>
      )}

      {projectsQuery.isError && (
        <p role="alert" className={styles.error}>
          {projectsQuery.error.message}
        </p>
      )}

      {projectsQuery.data?.length === 0 && (
        <p className={styles.message}>
          You do not currently have access to any projects.
        </p>
      )}

      {projectsQuery.data &&
        projectsQuery.data.length > 0 &&
        visibleProjects?.length === 0 && (
          <p className={styles.message}>
            All your projects are retired. Select “Show retired projects” to
            view them.
          </p>
        )}

      {visibleProjects && visibleProjects.length > 0 && (
        <ul className={styles.list}>
          {visibleProjects.map((project) => (
            <li key={project.name} className={styles.listItem}>
              <Link
                className={styles.projectLink}
                to={`/projects/${project.name}`}
              >
                {project.name}
              </Link>
              <span className={styles.status}>{project.status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export { ProjectList }
