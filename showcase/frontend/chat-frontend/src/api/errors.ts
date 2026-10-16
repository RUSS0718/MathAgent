export class ApiError extends Error {
  readonly status: number | null
  readonly code: string
  readonly requestId: string | null

  constructor(options: { status: number | null; code: string; message: string; requestId?: string | null; cause?: unknown }) {
    super(options.message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.requestId = options.requestId ?? null
    this.cause = options.cause
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}
