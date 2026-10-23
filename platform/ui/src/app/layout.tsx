import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@/components/ui/button'

function AppLayout() {
  const { status, signOut } = useAuth()
  return (
    <div className="min-h-svh bg-background text-foreground">
      <a
        className="sr-only fixed top-4 left-4 z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only"
        href="#main-content"
      >
        Skip to content
      </a>
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center px-4 sm:px-6 lg:px-8">
          <NavLink className="font-semibold tracking-tight" to="/">
            Developer Platform
          </NavLink>
          <span className="ml-3 text-sm text-muted-foreground">
            Control Plane
          </span>
          <nav className="ml-auto" aria-label="Primary navigation">
            <NavLink
              className="rounded-md px-3 py-2 text-sm"
              to="/store-access"
            >
              My store access
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`
              }
              to="/"
              end
            >
              Projects
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`
              }
              to="/platform/administration"
            >
              Platform admin
            </NavLink>
          </nav>
          {status === 'authenticated' && (
            <Button
              variant="outline"
              className="ml-3"
              onClick={() => void signOut()}
            >
              Log out
            </Button>
          )}
        </div>
      </header>
      <main
        id="main-content"
        className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8"
      >
        <Outlet />
      </main>
    </div>
  )
}

export { AppLayout }
