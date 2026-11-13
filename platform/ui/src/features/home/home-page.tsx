import { Alert, Badge, Button, Paper } from '@mantine/core'
import { useAuth } from '@/auth/auth-context'
import { ProjectList } from '@/features/projects/project-list'
import styles from './home-page.module.css'

function HomePage() {
  const { error, signIn, status, user } = useAuth()
  const subject =
    typeof user?.profile.sub === 'string' ? user.profile.sub : null
  const displayName =
    user?.profile.preferred_username ?? user?.profile.name ?? subject

  return (
    <section aria-labelledby="page-title" className={styles.page}>
      <Paper component="header" withBorder radius="lg" className={styles.hero}>
        <Badge variant="light" color="indigo">
          Platform workspace
        </Badge>
        <h1 id="page-title" className={styles.heading}>
          {status === 'authenticated'
            ? 'Your platform workspace'
            : 'Developer Platform portal'}
        </h1>
        <p className={styles.lead}>
          {status === 'authenticated'
            ? 'Choose a project to manage deployments, data stores, and application access.'
            : 'Sign in to find your projects and manage their applications, data, and access in one place.'}
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
          <Alert color="red" title="Sign-in unavailable" role="alert">
            {error}
          </Alert>
        )}
      </Paper>
      <ProjectList />
    </section>
  )
}

export { HomePage }
