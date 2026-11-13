import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@mantine/core'
import styles from './layout.module.css'

function AppLayout() {
  const { status, signOut } = useAuth()
  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content">
        Skip to content
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <NavLink className={styles.brand} to="/">
            Developer Platform
          </NavLink>
          <span className={styles.subtitle}>Control Plane</span>
          <nav className={styles.navigation} aria-label="Primary navigation">
            <NavLink className={styles.navLink} to="/store-access">
              My store access
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`
              }
              to="/"
              end
            >
              Projects
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`
              }
              to="/platform/administration"
            >
              Platform admin
            </NavLink>
          </nav>
          {status === 'authenticated' && (
            <Button
              variant="outline"
              className={styles.logout}
              onClick={() => void signOut()}
            >
              Log out
            </Button>
          )}
        </div>
      </header>
      <main id="main-content" className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}

export { AppLayout }
