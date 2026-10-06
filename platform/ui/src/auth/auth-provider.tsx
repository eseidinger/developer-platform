import * as React from 'react'
import type { User, UserManager } from 'oidc-client-ts'

import { setAccessTokenProvider } from '@/api/client'
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from '@/auth/auth-context'
import { loadPortalAuthConfig } from '@/auth/config'
import { createUserManager } from '@/auth/oidc-client'

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : 'Authentication could not be completed.'
}

function AuthProvider({ children }: React.PropsWithChildren) {
  const [manager, setManager] = React.useState<UserManager | null>(null)
  const [status, setStatus] = React.useState<AuthStatus>('loading')
  const [user, setUser] = React.useState<User | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const applyUser = React.useCallback((nextUser: User | null) => {
    const accessToken = nextUser?.access_token ?? null
    setAccessTokenProvider(() => accessToken)
    setUser(nextUser)
    setStatus(nextUser && !nextUser.expired ? 'authenticated' : 'anonymous')
  }, [])

  React.useEffect(() => {
    let active = true

    async function initialize() {
      try {
        const config = await loadPortalAuthConfig()
        const nextManager = createUserManager(config)
        const storedUser = await nextManager.getUser()

        if (!active) {
          return
        }

        setManager(nextManager)
        applyUser(storedUser?.expired ? null : storedUser)
      } catch (initializationError) {
        if (!active) {
          return
        }

        setError(messageFor(initializationError))
        setStatus('error')
      }
    }

    void initialize()

    return () => {
      active = false
    }
  }, [applyUser])

  React.useEffect(() => {
    if (!user?.expires_at) {
      return
    }

    const delay = Math.max(user.expires_at * 1000 - Date.now(), 0)
    const timeout = window.setTimeout(() => applyUser(null), delay)

    return () => window.clearTimeout(timeout)
  }, [applyUser, user])

  const signIn = React.useCallback(async () => {
    if (!manager) {
      setError('Authentication is still initializing.')
      return
    }

    try {
      setError(null)
      await manager.signinRedirect()
    } catch (signInError) {
      setError(messageFor(signInError))
      setStatus('error')
    }
  }, [manager])

  const completeSignIn = React.useCallback(
    async (url: string) => {
      if (!manager) {
        setError('Authentication is still initializing.')
        return false
      }

      try {
        setError(null)
        const signedInUser = await manager.signinCallback(url)
        applyUser(signedInUser ?? null)
        return true
      } catch (completionError) {
        setError(messageFor(completionError))
        setStatus('error')
        return false
      }
    },
    [applyUser, manager],
  )

  const signOut = React.useCallback(async () => {
    if (!manager) {
      return
    }

    applyUser(null)
    await manager.removeUser()
  }, [applyUser, manager])

  const value = React.useMemo<AuthContextValue>(
    () => ({ status, user, error, signIn, completeSignIn, signOut }),
    [status, user, error, signIn, completeSignIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export { AuthProvider }
