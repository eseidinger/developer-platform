import * as React from 'react'
import type { User } from 'oidc-client-ts'

type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'error'

type AuthContextValue = {
  status: AuthStatus
  user: User | null
  error: string | null
  signIn: () => Promise<void>
  completeSignIn: (url: string) => Promise<boolean>
  signOut: () => Promise<void>
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

function useAuth() {
  const context = React.useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.')
  }

  return context
}

export { AuthContext, useAuth }
export type { AuthContextValue, AuthStatus }
