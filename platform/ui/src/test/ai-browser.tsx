// Deterministic browser fixture; this entry is excluded from the production bundle.
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { createQueryClient } from '@/api/query-client'
import { AuthContext, type AuthContextValue } from '@/auth/auth-context'
import { AiAssistancePage } from '@/features/ai/ai-assistance-page'
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
  <QueryClientProvider client={createQueryClient()}>
    <AuthContext.Provider value={auth}>
      <BrowserRouter>
        <nav>
          <Link to="/projects/other/ai">Switch project</Link>
        </nav>
        <Routes>
          <Route path="/projects/:name/ai" element={<AiAssistancePage />} />
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  </QueryClientProvider>,
)
