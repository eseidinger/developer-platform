import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/auth/auth-context'
import { ProjectList } from '@/features/projects/project-list'

const foundationItems = [
  'Typed Platform API client generated from OpenAPI',
  'Route and query-provider application shell',
  'Component and browser-test foundations',
] as const

function HomePage() {
  const { error, signIn, signOut, status, user } = useAuth()
  const subject = typeof user?.profile.sub === 'string' ? user.profile.sub : null

  return (
    <section aria-labelledby="page-title" className="max-w-3xl space-y-8">
      <div className="space-y-3">
        <Badge variant="secondary">UI foundation</Badge>
        <h1 id="page-title" className="text-3xl font-semibold tracking-tight">
          Developer Platform portal
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          The portal foundation is ready for authenticated project discovery,
          deployment, and diagnostics work.
        </p>
        {status === 'loading' && (
          <p role="status" className="text-sm text-muted-foreground">
            Preparing secure sign-in…
          </p>
        )}
        {status === 'anonymous' && (
          <Button onClick={() => void signIn()}>Sign in with OIDC</Button>
        )}
        {status === 'authenticated' && (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">
              Signed in{subject ? ` as ${subject}` : ''}. Access is determined by platform-owned grants.
            </p>
            <Button variant="outline" onClick={() => void signOut()}>
              Clear portal session
            </Button>
          </div>
        )}
        {status === 'error' && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
      <section aria-labelledby="foundation-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
        <h2 id="foundation-title" className="text-lg font-medium">
          Current foundation
        </h2>
        <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
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
