// Browser-only fixture. This entry is not imported by the production app.
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createQueryClient } from '@/api/query-client'
import { AuthContext, type AuthContextValue } from '@/auth/auth-context'
import { HomePage } from '@/features/home/home-page'
import { ProjectWorkspace } from '@/features/projects/project-workspace'
import '../index.css'

const auth: AuthContextValue = { status: 'authenticated', user: null, error: null, signIn: () => Promise.resolve(), completeSignIn: () => Promise.resolve(false), signOut: () => Promise.resolve() }
const target = document.getElementById('root')
if (!target) throw new Error('Missing browser fixture root')
createRoot(target).render(
  <QueryClientProvider client={createQueryClient()}>
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects/:name" element={<ProjectWorkspace />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  </QueryClientProvider>,
)
