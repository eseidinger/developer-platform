import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/errors'
import { ProjectDatabaseAccess } from './project-database-access'
import {
  createHumanDatabaseGrant,
  getMyDatabaseAccess,
  issueMyDatabaseCredential,
  listHumanDatabaseGrants,
  replaceMyDatabaseKey,
  revokeHumanDatabaseGrant,
} from './database-access-api'

vi.mock('./database-access-api', () => ({
  createHumanDatabaseGrant: vi.fn(),
  getMyDatabaseAccess: vi.fn(),
  issueMyDatabaseCredential: vi.fn(),
  listHumanDatabaseGrants: vi.fn(),
  replaceMyDatabaseKey: vi.fn(),
  revokeHumanDatabaseGrant: vi.fn(),
}))

const grant = {
  project: 'demo',
  issuer: 'https://identity.example',
  subject: 'person-1',
  username: 'human_abc',
  keyFingerprint: 'SHA256:abc',
  active: true,
  createdAt: '2026-10-14T10:00:00Z',
  updatedAt: '2026-10-14T10:00:00Z',
}

function mount() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ProjectDatabaseAccess name="demo" enabled />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(getMyDatabaseAccess).mockResolvedValue({
    ...grant,
    database: 'project_demo',
    sshUser: 'platform-db',
  })
  vi.mocked(listHumanDatabaseGrants).mockResolvedValue([grant])
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('project human database controls', () => {
  it('hides admin controls on 403 while showing an ungranted personal state', async () => {
    vi.mocked(getMyDatabaseAccess).mockRejectedValue(
      new ApiError('No active grant', 404),
    )
    vi.mocked(listHumanDatabaseGrants).mockRejectedValue(
      new ApiError('Not authorized', 403),
    )
    mount()
    expect(
      await screen.findByText(
        'You do not have a personal database grant for this project.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Grant database access' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('submits an admin grant without showing SQL credentials', async () => {
    const user = userEvent.setup()
    vi.mocked(createHumanDatabaseGrant).mockResolvedValue(grant)
    mount()
    await user.click(
      await screen.findByRole('button', { name: 'Grant database access' }),
    )
    await user.type(screen.getByLabelText('Issuer'), 'https://identity.example')
    await user.type(screen.getByLabelText('Subject ID'), 'person-2')
    await user.type(screen.getByLabelText('SSH public key'), 'ssh-ed25519 AAAA')
    await user.click(screen.getByRole('button', { name: 'Grant access' }))
    await waitFor(() =>
      expect(createHumanDatabaseGrant).toHaveBeenCalledWith('demo', {
        issuer: 'https://identity.example',
        subject: 'person-2',
        publicKey: 'ssh-ed25519 AAAA',
      }),
    )
    expect(screen.queryByLabelText('One-time password')).not.toBeInTheDocument()
  })

  it('requires confirmation to revoke an active grant', async () => {
    const user = userEvent.setup()
    vi.mocked(revokeHumanDatabaseGrant).mockResolvedValue(undefined)
    mount()
    await user.click(await screen.findByRole('button', { name: 'Revoke' }))
    expect(revokeHumanDatabaseGrant).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Revoke access' }))
    await waitFor(() =>
      expect(revokeHumanDatabaseGrant).toHaveBeenCalledWith('demo', grant),
    )
  })

  it('removes the personal identity when a revoked grant refetch returns 404', async () => {
    const user = userEvent.setup()
    vi.mocked(getMyDatabaseAccess)
      .mockResolvedValueOnce({
        ...grant,
        database: 'project_demo',
        sshUser: 'platform-db',
      })
      .mockRejectedValueOnce(new ApiError('No active grant', 404))
    vi.mocked(listHumanDatabaseGrants)
      .mockResolvedValueOnce([grant])
      .mockResolvedValueOnce([{ ...grant, active: false }])
    vi.mocked(revokeHumanDatabaseGrant).mockResolvedValue(undefined)
    mount()
    expect(
      await screen.findByText('Your database identity'),
    ).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Revoke' }))
    await user.click(screen.getByRole('button', { name: 'Revoke access' }))
    expect(
      await screen.findByText(
        'You do not have a personal database grant for this project.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Your database identity')).not.toBeInTheDocument()
  })

  it('discards a one-time password when its dialog closes', async () => {
    const user = userEvent.setup()
    vi.mocked(issueMyDatabaseCredential).mockResolvedValue({
      project: 'demo',
      database: 'project_demo',
      username: 'human_abc',
      password: 'only-once',
    })
    mount()
    await user.click(
      await screen.findByRole('button', { name: 'Rotate SQL password' }),
    )
    await user.click(screen.getByRole('button', { name: 'Rotate password' }))
    expect(await screen.findByLabelText('One-time password')).toHaveValue(
      'only-once',
    )
    await user.click(
      screen.getByRole('button', { name: 'I saved the password' }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Rotate SQL password' }),
    )
    expect(screen.queryByLabelText('One-time password')).not.toBeInTheDocument()
    expect(issueMyDatabaseCredential).toHaveBeenCalledTimes(1)
  })

  it('lets the named person replace their public key', async () => {
    const user = userEvent.setup()
    vi.mocked(replaceMyDatabaseKey).mockResolvedValue(grant)
    mount()
    await user.click(
      await screen.findByRole('button', { name: 'Replace SSH key' }),
    )
    await user.type(
      screen.getByLabelText('New SSH public key'),
      'ssh-ed25519 BBBB',
    )
    await user.click(screen.getByRole('button', { name: 'Replace key' }))
    await waitFor(() =>
      expect(replaceMyDatabaseKey).toHaveBeenCalledWith(
        'demo',
        'ssh-ed25519 BBBB',
      ),
    )
  })
})
