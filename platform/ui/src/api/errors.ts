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

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function errorMessage(body: unknown) {
  const record = asRecord(body)
  if (!record) {
    return null
  }

  const detail = record.detail
  return typeof detail === 'string' ? detail : null
}

function errorCode(body: unknown) {
  const record = asRecord(body)
  if (!record) {
    return undefined
  }

  return typeof record.code === 'string' ? record.code : undefined
}

export function apiErrorFromResponse(response: Response, body: unknown) {
  return new ApiError(
    errorMessage(body) ?? `The platform request failed with status ${response.status}.`,
    response.status,
    errorCode(body),
  )
}
