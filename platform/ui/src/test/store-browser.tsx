// Browser-only store fixture. API responses are intercepted by Playwright.
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { createQueryClient } from '@/api/query-client'
import { PortalThemeProvider } from '@/app/theme'
import { AuthContext, type AuthContextValue } from '@/auth/auth-context'
import { StoresPage } from '@/features/stores/stores-page'
import '../index.css'

const auth: AuthContextValue = {
  status: 'authenticated',
  user: null,
  error: null,
  signIn: () => Promise.resolve(),
  completeSignIn: () => Promise.resolve(false),
  signOut: () => Promise.resolve(),
}

const target = document.getElementById('root')
if (!target) throw new Error('Missing browser fixture root')

createRoot(target).render(
  <PortalThemeProvider>
    <QueryClientProvider client={createQueryClient()}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={['/projects/alpha/stores']}>
          <Routes>
            <Route path="/projects/:name/stores" element={<StoresPage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  </PortalThemeProvider>,
)
