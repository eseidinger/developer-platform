import { AuthCallbackPage } from '@/auth/auth-callback-page'
import { HomePage } from '@/features/home/home-page'

function RootPage() {
  const search = new URLSearchParams(window.location.search)
  if (search.has('code') || search.has('error')) {
    return <AuthCallbackPage />
  }

  return <HomePage />
}

export { RootPage }
