import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { HomePage } from '@/features/home/home-page'

describe('HomePage', () => {
  it('describes the portal foundation', () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: 'Developer Platform portal' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Typed Platform API client generated from OpenAPI'),
    ).toBeInTheDocument()
  })
})
