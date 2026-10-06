import { Badge } from '@/components/ui/badge'

const foundationItems = [
  'Typed Platform API client generated from OpenAPI',
  'Route and query-provider application shell',
  'Component and browser-test foundations',
] as const

function HomePage() {
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
    </section>
  )
}

export { HomePage }
