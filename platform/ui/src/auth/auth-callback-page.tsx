import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/auth/auth-context'
import styles from './auth-callback-page.module.css'

function AuthCallbackPage() {
  const { completeSignIn, error, status } = useAuth()
  const navigate = useNavigate()
  const completed = React.useRef(false)

  React.useEffect(() => {
    if (status === 'loading' || completed.current) {
      return
    }

    completed.current = true

    let active = true

    async function complete() {
      try {
        const signedIn = await completeSignIn(window.location.href)
        if (active && signedIn) {
          window.history.replaceState(
            {},
            document.title,
            window.location.pathname,
          )
          void navigate('/', { replace: true })
        }
      } catch {
        // The provider turns all expected authentication failures into safe state.
      }
    }

    void complete()

    return () => {
      active = false
    }
  }, [completeSignIn, navigate, status])

  if (error) {
    return (
      <section aria-labelledby="callback-title" className={styles.panel}>
        <h1 id="callback-title" className={styles.heading}>
          Sign-in could not be completed
        </h1>
        <p className={styles.message}>{error}</p>
      </section>
    )
  }

  return (
    <section aria-labelledby="callback-title" className={styles.panel}>
      <h1 id="callback-title" className={styles.heading}>
        Completing sign-in
      </h1>
      <p className={styles.message}>
        Verifying the identity-provider response.
      </p>
    </section>
  )
}

export { AuthCallbackPage }
