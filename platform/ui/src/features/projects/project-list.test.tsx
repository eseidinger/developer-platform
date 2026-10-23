import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProjectList } from '@/features/projects/project-list'

vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ status: 'authenticated' }),
}))

afterEach(cleanup)

function renderProjects(projects: { name: string; status: string }[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity } },
  })
  client.setQueryData(['projects'], projects)
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectList />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

describe('ProjectList', () => {
  it('hides retired projects by default and allows showing and hiding them', async () => {
    const user = renderProjects([
      { name: 'normal-app', status: 'applied' },
      { name: 'failed-app', status: 'failed' },
      { name: 'old-fixture', status: 'retired' },
    ])
    expect(screen.getByRole('link', { name: 'normal-app' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'failed-app' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'old-fixture' })).toBeNull()
    const filter = screen.getByRole('checkbox', {
      name: 'Show retired projects',
    })
    await user.click(filter)
    expect(
      screen.getByRole('link', { name: 'old-fixture' }),
    ).toBeInTheDocument()
    await user.click(filter)
    expect(screen.queryByRole('link', { name: 'old-fixture' })).toBeNull()
  })

  it('explains when all projects are hidden by the filter', async () => {
    const user = renderProjects([{ name: 'old-fixture', status: 'retired' }])
    expect(
      screen.getByText(/All your projects are retired/),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('checkbox', { name: 'Show retired projects' }),
    )
    expect(screen.queryByText(/All your projects are retired/)).toBeNull()
    expect(
      screen.getByRole('link', { name: 'old-fixture' }),
    ).toBeInTheDocument()
  })

  it('retains the empty message for accounts without projects', () => {
    renderProjects([])
    expect(
      screen.getByText('You do not currently have access to any projects.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/All your projects are retired/)).toBeNull()
  })
})
