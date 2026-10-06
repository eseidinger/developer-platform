import { QueryClient } from '@tanstack/react-query'

import { isTransientApiError } from '@/api/errors'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) =>
          failureCount < 2 && isTransientApiError(error),
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
}
