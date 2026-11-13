import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'

import { createQueryClient } from '@/api/query-client'
import { AuthProvider } from '@/auth/auth-provider'
import { PortalThemeProvider } from '@/app/theme'
import './index.css'
import App from './App.tsx'

const queryClient = createQueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <PortalThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </PortalThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
