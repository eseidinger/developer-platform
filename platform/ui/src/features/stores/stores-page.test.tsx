import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { StoresPage } from './stores-page'
import * as api from './stores-api'

vi.mock('./stores-api')
vi.mock('@/auth/auth-context', () => ({ useAuth: () => ({ status: 'authenticated', user: { profile: { iss: 'https://fixture.invalid', sub: 'human' } } }) }))
const resource = { resource_id: '12345678-1234-4234-8234-123456789abc', owner_project: 'alpha', name: 'primary', provider: 'postgresql',
  state: 'active', observed_state: 'active', version: 1, quota_bytes: 1073741824, extensions: [], error_code: null }
const grant = { grant_id: '22345678-1234-4234-8234-123456789abc', resource_id: resource.resource_id, kind: 'human' as const,
  issuer: 'https://fixture.invalid', subject: 'human', consumer_project: null, component: null,
  mode: 'read-write' as const, state: 'active', observed_state: 'active', version: 1, error_code: null }
const pending = { credential_id: '32345678-1234-4234-8234-123456789abc', grant_id: grant.grant_id, state: 'issuing',
  expires_at: new Date(Date.now() + 86400000).toISOString(), issued_at: new Date().toISOString() }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getContext).mockResolvedValue({ manage: false, platform_admin: false, providers: [{ id: 'postgresql', enabled: true }] })
  vi.mocked(api.getResources).mockResolvedValue([])
  vi.mocked(api.getBindings).mockResolvedValue([])
  vi.mocked(api.getGrants).mockResolvedValue([])
  vi.mocked(api.getMine).mockResolvedValue([])
  vi.mocked(api.leases).mockResolvedValue([])
})
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/projects/alpha/stores']}><Routes><Route path="/projects/:name/stores" element={<StoresPage />} /></Routes></MemoryRouter></QueryClientProvider>)
  return { client, user: userEvent.setup() }
}
test('viewers see only personal grants and never load administration lists', async () => {
  setup()
  expect(await screen.findByText('No named-resource human grants. An administrator must grant access explicitly.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Create resource' })).not.toBeInTheDocument()
  expect(api.getResources).not.toHaveBeenCalled()
  expect(api.getBindings).not.toHaveBeenCalled()
  expect(api.issue).not.toHaveBeenCalled()
})
test('creating a resource does not implicitly bind an application', async () => {
  vi.mocked(api.getContext).mockResolvedValue({ manage: true, platform_admin: false, providers: [{ id: 'postgresql', enabled: true }] })
  vi.mocked(api.createResource).mockResolvedValue(resource)
  const { user } = setup()
  await user.type(await screen.findByLabelText('Resource name'), 'primary')
  expect(api.createResource).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Create resource' }))
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith('alpha', { name: 'primary', provider: 'postgresql', quota_bytes: 1073741824, extensions: [] }))
  expect(api.requestBinding).not.toHaveBeenCalled()
  expect(api.createHuman).not.toHaveBeenCalled()
})
test('credential issuance is explicit and pending provisioning never retries the POST', async () => {
  vi.mocked(api.getMine).mockResolvedValue([{ grant, resource }])
  vi.mocked(api.issue).mockResolvedValue(pending)
  vi.mocked(api.reveal).mockResolvedValue({ ...pending, state: 'active', connection: { PGHOST: '172.30.80.15', PGPORT: '20000', PGPASSWORD: 'seed-private-password' } })
  const { user, client } = setup()
  await user.click(await screen.findByRole('button', { name: 'Issue 24-hour credential' }))
  expect(await screen.findByText('Credential provisioning is pending. Inspect this lease again; do not issue another one.')).toBeInTheDocument()
  expect(api.issue).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Check credential readiness' }))
  expect(await screen.findByDisplayValue('seed-private-password')).toHaveAttribute('type', 'password')
  expect(api.issue).toHaveBeenCalledTimes(1)
  expect(JSON.stringify(client.getQueryCache().findAll().map(q => q.state.data))).not.toContain('seed-private-password')
  await user.click(screen.getByRole('button', { name: 'Close and discard credential' }))
  expect(screen.queryByDisplayValue('seed-private-password')).not.toBeInTheDocument()
})
test('console launch sends an ephemeral POST assertion without caching it or placing it in a URL', async () => {
  vi.mocked(api.getMine).mockResolvedValue([{ grant, resource: { ...resource, provider: 'qdrant', console_url: '/store-access' } }])
  vi.mocked(api.leases).mockResolvedValue([{ ...pending, state: 'active' }])
  vi.mocked(api.reveal).mockResolvedValue({ ...pending, state: 'active', connection: { QDRANT_API_KEY: 'seed-private-password' } })
  vi.mocked(api.launchConsole).mockResolvedValue({ url: 'https://console-20000.apps.fixture.invalid/__platform/start', launch: 'seed-ephemeral-assertion' })
  const submitted: { action: string; method: string; value: string }[] = []
  const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(function (this: HTMLFormElement) {
    submitted.push({ action: this.action, method: this.method, value: (this.elements.namedItem('launch') as HTMLInputElement).value })
  })
  try {
    const { user, client } = setup()
    await user.click(await screen.findByRole('button', { name: 'Inspect this lease' }))
    await user.click(await screen.findByRole('button', { name: 'Open Qdrant console' }))
    await waitFor(() => expect(submitted).toHaveLength(1))
    expect(submitted[0]).toEqual({ action: 'https://console-20000.apps.fixture.invalid/__platform/start', method: 'post', value: 'seed-ephemeral-assertion' })
    expect(document.querySelector('input[name="launch"]')).toBeNull()
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('seed-ephemeral-assertion')
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('seed-private-password')
  } finally { submit.mockRestore() }
})
