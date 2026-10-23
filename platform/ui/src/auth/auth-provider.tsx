import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { User, UserManager } from 'oidc-client-ts'

import { setAccessTokenProvider } from '@/api/client'
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from '@/auth/auth-context'
import { loadPortalAuthConfig } from '@/auth/config'
import { createUserManager } from '@/auth/oidc-client'

// This flag allows silent SSO after reload without persisting any tokens.
const SESSION_KEY = 'platform.portal.signed-in'

function messageFor(error: unknown) {
  return error instanceof Error
    ? error.message
    : 'Authentication could not be completed.'
}

function AuthProvider({ children }: React.PropsWithChildren) {
  const queryClient = useQueryClient()
  const signingOut = React.useRef(false)
  const [manager, setManager] = React.useState<UserManager | null>(null)
  const [status, setStatus] = React.useState<AuthStatus>('loading')
  const [user, setUser] = React.useState<User | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const applyUser = React.useCallback((nextUser: User | null) => {
    if (signingOut.current && nextUser) return
    if (nextUser?.expired) nextUser = null
    const accessToken = nextUser?.access_token ?? null
    setAccessTokenProvider(() => accessToken)
    setUser(nextUser)
    setStatus(nextUser ? 'authenticated' : 'anonymous')
    if (nextUser) {
      window.sessionStorage.setItem(SESSION_KEY, 'true')
      setError(null)
    }
  }, [])

  React.useEffect(() => {
    let active = true
    let dispose: (() => void) | undefined

    async function initialize() {
      try {
        const config = await loadPortalAuthConfig()
        const nextManager = createUserManager(config)
        if (!active) {
          nextManager.stopSilentRenew()
          return
        }

        const userLoaded = (nextUser: User) => {
          if (active) applyUser(nextUser)
        }
        const userUnloaded = () => {
          if (!active) return
          applyUser(null)
          queryClient.clear()
        }
        const renewError = () => {
          if (active && !signingOut.current) {
            setError(
              'Your session could not be renewed. Sign in again if it expires.',
            )
          }
        }
        nextManager.events.addUserLoaded(userLoaded)
        nextManager.events.addUserUnloaded(userUnloaded)
        nextManager.events.addAccessTokenExpired(userUnloaded)
        nextManager.events.addSilentRenewError(renewError)
        dispose = () => {
          nextManager.stopSilentRenew()
          nextManager.events.removeUserLoaded(userLoaded)
          nextManager.events.removeUserUnloaded(userUnloaded)
          nextManager.events.removeAccessTokenExpired(userUnloaded)
          nextManager.events.removeSilentRenewError(renewError)
        }
        setManager(nextManager)
        let storedUser = await nextManager.getUser()
        if (!active) return
        // A callback must complete its own OIDC transaction, including when it
        // runs inside the silent-signin iframe. Never start another one there.
        const search = new URLSearchParams(window.location.search)
        if (
          !storedUser &&
          !search.has('code') &&
          !search.has('error') &&
          window.sessionStorage.getItem(SESSION_KEY) === 'true'
        ) {
          try {
            storedUser = await nextManager.signinSilent()
          } catch {
            // Expired SSO and blocked third-party cookies require an explicit
            // sign-in. Do not redirect repeatedly or expose provider details.
            window.sessionStorage.removeItem(SESSION_KEY)
          }
        }
        if (active) applyUser(storedUser)
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
      dispose?.()
    }
  }, [applyUser, queryClient])

  const signIn = React.useCallback(async () => {
    if (!manager) {
      setError('Authentication is still initializing.')
      return
    }

    try {
      signingOut.current = false
      manager.startSilentRenew()
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

    signingOut.current = true
    manager.stopSilentRenew()
    window.sessionStorage.removeItem(SESSION_KEY)
    applyUser(null)
    queryClient.clear()
    try {
      // Keep the ID token available to the client for RP-initiated logout,
      // while immediately removing API access and cached private data above.
      await manager.signoutRedirect()
    } catch {
      setError(
        'The portal session was cleared, but identity-provider logout could not be completed.',
      )
    } finally {
      await manager.removeUser()
    }
  }, [applyUser, manager, queryClient])

  const value = React.useMemo<AuthContextValue>(
    () => ({ status, user, error, signIn, completeSignIn, signOut }),
    [status, user, error, signIn, completeSignIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export { AuthProvider }
