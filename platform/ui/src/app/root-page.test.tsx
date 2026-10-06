import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { RootPage } from '@/app/root-page'

vi.mock('@/auth/auth-callback-page', () => ({
  AuthCallbackPage: () => <p>Callback</p>,
}))

vi.mock('@/features/home/home-page', () => ({
  HomePage: () => <p>Home</p>,
}))

describe('RootPage', () => {
  it('renders the callback from the router query string', () => {
    render(
      <MemoryRouter initialEntries={['/?code=authorization-code&state=state']}>
        <Routes>
          <Route path="/" element={<RootPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Callback')).toBeInTheDocument()
  })
})
