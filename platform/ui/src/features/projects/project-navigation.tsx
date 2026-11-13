import { Link, useLocation } from 'react-router-dom'

import styles from './project-navigation.module.css'

type ProjectSection = 'overview' | 'application-access' | 'stores' | 'ai'

const sections: { id: ProjectSection; label: string; path: string }[] = [
  { id: 'overview', label: 'Overview', path: '' },
  {
    id: 'application-access',
    label: 'Application access',
    path: '/application-access',
  },
  { id: 'stores', label: 'Data stores', path: '/stores' },
  { id: 'ai', label: 'AI assistance', path: '/ai' },
]

function ProjectNavigation({ name }: { name: string }) {
  const { pathname } = useLocation()
  const basePath = `/projects/${encodeURIComponent(name)}`

  return (
    <nav aria-label={`${name} sections`} className={styles.navigation}>
      {sections.map((section) => {
        const to = `${basePath}${section.path}`
        const active = pathname === to
        return (
          <Link
            key={section.id}
            to={to}
            aria-current={active ? 'page' : undefined}
            className={`${styles.link} ${active ? styles.active : ''}`}
          >
            {section.label}
          </Link>
        )
      })}
    </nav>
  )
}

export { ProjectNavigation }
