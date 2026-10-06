import { useLocation } from 'react-router-dom'

import { AuthCallbackPage } from '@/auth/auth-callback-page'
import { HomePage } from '@/features/home/home-page'

function RootPage() {
  const { search: locationSearch } = useLocation()
  const search = new URLSearchParams(locationSearch)
  if (search.has('code') || search.has('error')) {
    return <AuthCallbackPage />
  }

  return <HomePage />
}

export { RootPage }
