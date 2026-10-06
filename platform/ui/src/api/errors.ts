export class ApiError extends Error {
  readonly status: number
  readonly code: string | undefined

  constructor(
    message: string,
    status: number,
    code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function isTransientApiError(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.status === 429 || error.status >= 500)
  )
}
