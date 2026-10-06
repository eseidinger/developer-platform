import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AuthContext, type AuthContextValue } from '@/auth/auth-context'
import { HomePage } from '@/features/home/home-page'

const anonymousAuth: AuthContextValue = {
  status: 'anonymous',
  user: null,
  error: null,
  signIn: () => Promise.resolve(),
  completeSignIn: () => Promise.resolve(false),
  signOut: () => Promise.resolve(),
}

describe('HomePage', () => {
  it('describes the portal foundation', () => {
    const queryClient = new QueryClient()

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthContext.Provider value={anonymousAuth}>
            <HomePage />
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      screen.getByRole('heading', { name: 'Developer Platform portal' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Typed Platform API client generated from OpenAPI'),
    ).toBeInTheDocument()
  })
})
