import { Badge } from '@mantine/core'
import { Button } from '@mantine/core'
import { useAuth } from '@/auth/auth-context'
import { ProjectList } from '@/features/projects/project-list'
import styles from './home-page.module.css'

const foundationItems = [
  'Typed Platform API client generated from OpenAPI',
  'Route and query-provider application shell',
  'Component and browser-test foundations',
] as const

function HomePage() {
  const { error, signIn, status, user } = useAuth()
  const subject =
    typeof user?.profile.sub === 'string' ? user.profile.sub : null
  const displayName =
    user?.profile.preferred_username ?? user?.profile.name ?? subject

  return (
    <section aria-labelledby="page-title" className={styles.page}>
      <div className={styles.intro}>
        <Badge variant="light" color="gray">
          UI foundation
        </Badge>
        <h1 id="page-title" className={styles.heading}>
          Developer Platform portal
        </h1>
        <p className={styles.lead}>
          The portal foundation is ready for authenticated project discovery,
          deployment, and diagnostics work.
        </p>
        {status === 'loading' && (
          <p role="status" className={styles.mutedSmall}>
            Preparing secure sign-in…
          </p>
        )}
        {status === 'anonymous' && (
          <Button onClick={() => void signIn()}>Sign in with OIDC</Button>
        )}
        {status === 'authenticated' && (
          <div className={styles.signedIn}>
            <p className={styles.mutedSmall}>
              Signed in{displayName ? ` as ${displayName}` : ''}. Access is
              determined by platform-owned grants.
            </p>
          </div>
        )}
        {error && (
          <p role="alert" className={styles.error}>
            {error}
          </p>
        )}
      </div>
      <section aria-labelledby="foundation-title" className={styles.panel}>
        <h2 id="foundation-title" className={styles.sectionHeading}>
          Current foundation
        </h2>
        <ul className={styles.foundationList}>
          {foundationItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      <ProjectList />
    </section>
  )
}

export { HomePage }
