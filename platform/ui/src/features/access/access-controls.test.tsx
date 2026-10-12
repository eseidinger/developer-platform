import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import { AccessDialog, Field } from './access-controls'

function wrap(children: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>{children}</QueryClientProvider>) }
afterEach(cleanup)
describe('versioned access actions', () => {
  it('preserves a draft and requires explicit reload and a fresh submission after conflict', async () => {
    const user = userEvent.setup()
    const submit = vi.fn<(version: number | undefined) => Promise<{ id: string; version: number; state: string }>>().mockRejectedValueOnce(new ApiError('Resource version changed', 412)).mockResolvedValueOnce({ id: 'pol_a', version: 3, state: 'provisioning' })
    const reload = vi.fn().mockResolvedValue({ id: 'pol_a', version: 2, state: 'active' })
    const close = vi.fn()
    wrap(<AccessDialog title="Edit policy" description="Review the policy" submitLabel="Save policy" resource={{ id: 'pol_a', version: 1, state: 'active' }} reload={reload} submit={submit} onAccepted={vi.fn().mockResolvedValue(undefined)} onClose={close}><Field label="Draft route" defaultValue="/app/" /></AccessDialog>)
    await user.type(screen.getByLabelText('Draft route'), 'draft')
    await user.click(screen.getByRole('button', { name: 'Save policy' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Resource version changed')
    expect(screen.getByRole('button', { name: 'Save policy' })).toBeDisabled()
    expect(submit).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Reload current version' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save policy' })).toBeEnabled())
    expect(screen.getByLabelText('Draft route')).toHaveValue('/app/draft')
    expect(submit).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Save policy' }))
    await waitFor(() => expect(close).toHaveBeenCalled())
    expect(submit.mock.calls.map((call) => call[0])).toEqual([1, 2])
  })
  it('latches double submission and keeps controls disabled during an operation', async () => {
    let finish!: (result: { id: string; state: string; version: number }) => void
    const submit = vi.fn(() => new Promise<{ id: string; state: string; version: number }>((resolve) => { finish = resolve }))
    wrap(<AccessDialog title="Approve request" description="No implicit groups" submitLabel="Approve" submit={submit} onAccepted={vi.fn().mockResolvedValue(undefined)} onClose={vi.fn()} />)
    const form = screen.getByRole('button', { name: 'Approve' }).closest('form')!
    fireEvent.submit(form); fireEvent.submit(form)
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('button', { name: 'Submitting…' })).toBeDisabled()
    await act(async () => { finish({ id: 'req_a', state: 'approved', version: 2 }); await Promise.resolve() })
  })
})
