import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { User } from 'oidc-client-ts'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setAccessTokenProvider } from '@/api/client'
import { AppLayout } from '@/app/layout'
import { useAuth } from '@/auth/auth-context'
import { AuthProvider } from '@/auth/auth-provider'

const mocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  signinSilent: vi.fn(),
  signinCallback: vi.fn(),
  signinRedirect: vi.fn(),
  signoutRedirect: vi.fn(),
  removeUser: vi.fn(),
  startSilentRenew: vi.fn(),
  stopSilentRenew: vi.fn(),
  events: {
    addUserLoaded: vi.fn(),
    removeUserLoaded: vi.fn(),
    addUserUnloaded: vi.fn(),
    removeUserUnloaded: vi.fn(),
    addAccessTokenExpired: vi.fn(),
    removeAccessTokenExpired: vi.fn(),
    addSilentRenewError: vi.fn(),
    removeSilentRenewError: vi.fn(),
  },
}))
vi.mock('@/auth/config', () => ({
  loadPortalAuthConfig: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/auth/oidc-client', () => ({ createUserManager: () => mocks }))
vi.mock('@/api/client', () => ({ setAccessTokenProvider: vi.fn() }))

function signedInUser(token = 'access-one') {
  return new User({
    access_token: token,
    refresh_token: 'refresh',
    token_type: 'Bearer',
    profile: {
      iss: 'https://identity.example',
      sub: 'alice',
      aud: 'portal',
      exp: 9999999999,
      iat: 1,
    },
    expires_at: Math.floor(Date.now() / 1000) + 300,
  })
}

function Session() {
  const { status, user, error, completeSignIn } = useAuth()
  return (
    <>
      <p>{status}</p>
      <p>{user?.access_token}</p>
      <p>{error}</p>
      <button onClick={() => void completeSignIn(window.location.href)}>
        Complete sign-in
      </button>
    </>
  )
}
function renderSession() {
  const client = new QueryClient()
  client.setQueryData(['private'], 'private data')
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter>
          <AppLayout />
          <Session />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
  return client
}

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
  mocks.getUser.mockResolvedValue(null)
})
afterEach(cleanup)

describe('portal session', () => {
  it('updates API credentials when automatic renewal loads a new token', async () => {
    mocks.getUser.mockResolvedValue(signedInUser())
    renderSession()
    await screen.findByText('authenticated')
    act(() => {
      const loaded = mocks.events.addUserLoaded.mock.calls.at(0)?.[0] as (
        user: User,
      ) => void
      loaded(signedInUser('renewed-access'))
    })
    expect(screen.getByText('renewed-access')).toBeInTheDocument()
    const provider = vi.mocked(setAccessTokenProvider).mock.lastCall?.[0]
    expect(provider?.()).toBe('renewed-access')
    expect(sessionStorage.getItem('platform.portal.signed-in')).toBe('true')
    expect(JSON.stringify(sessionStorage)).not.toContain('renewed-access')
  })

  it('silently restores a remembered session after reload', async () => {
    sessionStorage.setItem('platform.portal.signed-in', 'true')
    mocks.signinSilent.mockResolvedValue(signedInUser())
    renderSession()
    await screen.findByText('authenticated')
    expect(mocks.signinSilent).toHaveBeenCalledOnce()
  })

  it('does not start another sign-in while processing an OIDC callback', async () => {
    sessionStorage.setItem('platform.portal.signed-in', 'true')
    window.history.replaceState({}, '', '/?code=code&state=state')
    mocks.signinCallback.mockResolvedValue(signedInUser())
    renderSession()
    await screen.findByText('anonymous')
    expect(mocks.signinSilent).not.toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Complete sign-in' }),
    )
    await screen.findByText('authenticated')
  })

  it('falls back to explicit sign-in when silent SSO is unavailable', async () => {
    sessionStorage.setItem('platform.portal.signed-in', 'true')
    mocks.signinSilent.mockRejectedValue(new Error('login_required'))
    renderSession()
    await screen.findByText('anonymous')
    expect(mocks.signinRedirect).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('platform.portal.signed-in')).toBeNull()
  })

  it('clears private data on expiry and handles renewal failure without discarding a valid token', async () => {
    mocks.getUser.mockResolvedValue(signedInUser())
    const client = renderSession()
    await screen.findByText('authenticated')
    act(() => {
      const failed = mocks.events.addSilentRenewError.mock.calls.at(
        0,
      )?.[0] as () => void
      failed()
    })
    expect(screen.getByText('authenticated')).toBeInTheDocument()
    expect(screen.getByText(/session could not be renewed/)).toBeInTheDocument()
    act(() => {
      const expired = mocks.events.addAccessTokenExpired.mock.calls.at(
        0,
      )?.[0] as () => void
      expired()
    })
    expect(screen.getByText('anonymous')).toBeInTheDocument()
    expect(client.getQueryData(['private'])).toBeUndefined()
    const provider = vi.mocked(setAccessTokenProvider).mock.lastCall?.[0]
    expect(provider?.()).toBeNull()
  })

  it('ends the provider session, clears cached data, and ignores late renewal', async () => {
    mocks.getUser.mockResolvedValue(signedInUser())
    const client = renderSession()
    await screen.findByText('authenticated')
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(screen.getByText('anonymous')).toBeInTheDocument()
    expect(mocks.stopSilentRenew).toHaveBeenCalled()
    expect(mocks.signoutRedirect).toHaveBeenCalledOnce()
    expect(mocks.removeUser).toHaveBeenCalledOnce()
    expect(sessionStorage.getItem('platform.portal.signed-in')).toBeNull()
    expect(client.getQueryData(['private'])).toBeUndefined()
    act(() => {
      const loaded = mocks.events.addUserLoaded.mock.calls.at(0)?.[0] as (
        user: User,
      ) => void
      loaded(signedInUser('late-token'))
    })
    expect(screen.queryByText('late-token')).toBeNull()
  })

  it('still clears local credentials if identity-provider logout fails', async () => {
    mocks.getUser.mockResolvedValue(signedInUser())
    mocks.signoutRedirect.mockRejectedValue(new Error('offline'))
    renderSession()
    await screen.findByText('authenticated')
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(mocks.removeUser).toHaveBeenCalledOnce())
    expect(screen.getByText('anonymous')).toBeInTheDocument()
    expect(
      screen.getByText(/identity-provider logout could not be completed/),
    ).toBeInTheDocument()
  })
})
