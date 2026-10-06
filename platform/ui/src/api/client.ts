import createClient from 'openapi-fetch'

import type { paths } from '@/api/generated/schema'

type AccessTokenProvider = () => string | null

let accessTokenProvider: AccessTokenProvider = () => null

const baseUrl = import.meta.env.VITE_PLATFORM_API_BASE_URL ?? ''

export const apiClient = createClient<paths>({ baseUrl })

apiClient.use({
  onRequest({ request }) {
    const accessToken = accessTokenProvider()
    if (accessToken) {
      request.headers.set('Authorization', `Bearer ${accessToken}`)
    }

    return request
  },
})

export function setAccessTokenProvider(provider: AccessTokenProvider) {
  accessTokenProvider = provider
}
