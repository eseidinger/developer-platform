// Browser-only deterministic fixture. This entry is not imported by the production app.
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createQueryClient } from '@/api/query-client'
import { AuthContext, type AuthContextValue } from '@/auth/auth-context'
import { ApplicationAccessPage } from '@/features/access/application-access-page'
import '../index.css'

const auth: AuthContextValue = { status: 'authenticated', user: null, error: null, signIn: () => Promise.resolve(), completeSignIn: () => Promise.resolve(false), signOut: () => Promise.resolve() }
const params = new URLSearchParams(window.location.search)
const project = params.get('project') ?? 'provider'
const view = params.get('view') ?? 'overview'
const target = document.getElementById('root')
if (!target) throw new Error('Missing browser fixture root')
createRoot(target).render(<QueryClientProvider client={createQueryClient()}><AuthContext.Provider value={auth}><MemoryRouter initialEntries={[`/projects/${project}/application-access?view=${view}`]}><Routes><Route path="/projects/:name/application-access" element={<ApplicationAccessPage />} /></Routes></MemoryRouter></AuthContext.Provider></QueryClientProvider>)
