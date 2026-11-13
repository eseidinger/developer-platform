import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { AppShell, Burger, Button, Drawer } from '@mantine/core'

import { useAuth } from '@/auth/auth-context'
import styles from './layout.module.css'

function PrimaryNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation()
  const destinations = [
    {
      label: 'Projects',
      to: '/',
      active: pathname === '/' || pathname.startsWith('/projects/'),
    },
    {
      label: 'My store access',
      to: '/store-access',
      active: pathname === '/store-access',
    },
    {
      label: 'Platform admin',
      to: '/platform/administration',
      active: pathname === '/platform/administration',
    },
  ]

  return (
    <nav className={styles.navigation} aria-label="Primary navigation">
      {destinations.map(({ label, to, active }) => (
        <Link
          key={to}
          to={to}
          aria-current={active ? 'page' : undefined}
          className={`${styles.navLink} ${active ? styles.navLinkActive : ''}`}
          onClick={onNavigate}
        >
          <span className={styles.navIndicator} aria-hidden="true" />
          {label}
        </Link>
      ))}
    </nav>
  )
}

function AppLayout() {
  const { status, user, signOut } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const displayName = user?.profile.preferred_username ?? user?.profile.name

  return (
    <AppShell
      header={{ height: 72 }}
      navbar={{ width: 248, breakpoint: 'sm', collapsed: { mobile: true } }}
      padding={0}
      className={styles.shell}
    >
      <a className={styles.skipLink} href="#main-content">
        Skip to content
      </a>
      <AppShell.Header className={styles.header}>
        <div className={styles.headerInner}>
          <Burger
            className={styles.menuButton}
            opened={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            size="sm"
          />
          <Link className={styles.brand} to="/">
            <span className={styles.brandMark} aria-hidden="true">
              D
            </span>
            <span>
              <strong>Developer Platform</strong>
              <small>Control Plane</small>
            </span>
          </Link>
          <div className={styles.session}>
            {status === 'authenticated' && (
              <>
                {displayName && (
                  <span className={styles.identity}>{displayName}</span>
                )}
                <Button
                  variant="subtle"
                  size="sm"
                  onClick={() => void signOut()}
                >
                  Log out
                </Button>
              </>
            )}
          </div>
        </div>
      </AppShell.Header>
      <AppShell.Navbar className={styles.sidebar}>
        <div className={styles.sidebarInner}>
          <p className={styles.sidebarLabel}>Workspace</p>
          <PrimaryNavigation />
          <p className={styles.sidebarFootnote}>
            Your platform access follows your current grants.
          </p>
        </div>
      </AppShell.Navbar>
      <Drawer
        opened={menuOpen}
        onClose={() => setMenuOpen(false)}
        title="Workspace navigation"
        size="18rem"
        classNames={{ body: styles.drawerBody }}
      >
        <PrimaryNavigation onNavigate={() => setMenuOpen(false)} />
      </Drawer>
      <AppShell.Main id="main-content" className={styles.main}>
        <div className={styles.mainInner}>
          <Outlet />
        </div>
      </AppShell.Main>
    </AppShell>
  )
}

export { AppLayout }
