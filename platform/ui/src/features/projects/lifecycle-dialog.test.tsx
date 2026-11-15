import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { cleanup, render, screen, waitFor, within } from '@/test/render'
import { LifecycleDialog } from './lifecycle-dialog'
import { getLifecyclePreview, startLifecycle } from './lifecycle-api'

vi.mock('./lifecycle-api', () => ({
  getLifecyclePreview: vi.fn(),
  startLifecycle: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('waits for a fresh scope before confirming a cached lifecycle preview', async () => {
  const cached = {
    project: 'demo',
    project_id: '147bc94b-7279-4e56-a452-89e187f47b5b',
    action: 'restore' as const,
    status: 'retired',
    scope_token: 'old-scope',
    inventory: {
      workloads: [],
      named_store_resources: [],
      named_store_grants: [],
    },
    blockers: [],
  }
  const fresh = { ...cached, scope_token: 'current-scope' }
  let resolvePreview!: (value: typeof cached) => void
  vi.mocked(getLifecyclePreview).mockReturnValue(
    new Promise((resolve) => {
      resolvePreview = resolve
    }),
  )
  vi.mocked(startLifecycle).mockResolvedValue({
    operation_id: '859e3df3-890c-4c7d-8eda-2194d8cd78d3',
    state: 'queued',
    status_url: '/v1/operations/859e3df3-890c-4c7d-8eda-2194d8cd78d3',
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  client.setQueryData(['projects', 'demo', 'restore', 'preview'], cached)
  render(
    <QueryClientProvider client={client}>
      <LifecycleDialog name="demo" action="restore" onAccepted={vi.fn()} />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Restore project' }))
  const dialog = within(screen.getByRole('dialog'))
  await user.type(dialog.getByLabelText('Type demo to confirm'), 'demo')
  const confirm = dialog.getByRole('button', { name: 'Restore project' })
  expect(confirm).toBeDisabled()
  expect(dialog.getByRole('status')).toHaveTextContent('Loading project scope')
  expect(startLifecycle).not.toHaveBeenCalled()

  resolvePreview(fresh)
  await waitFor(() => expect(confirm).toBeEnabled())
  await user.click(confirm)
  expect(startLifecycle).toHaveBeenCalledWith(fresh)
})
