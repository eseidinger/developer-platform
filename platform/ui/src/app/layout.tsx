import { Outlet } from 'react-router-dom'

function AppLayout() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <a
        className="sr-only fixed left-4 top-4 z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only"
        href="#main-content"
      >
        Skip to content
      </a>
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center px-4 sm:px-6 lg:px-8">
          <span className="font-semibold tracking-tight">Developer Platform</span>
          <span className="ml-3 text-sm text-muted-foreground">Control Plane</span>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  )
}

export { AppLayout }
