import type { ApiErrorCode } from './types'

export class ApiError extends Error {
  code: ApiErrorCode

  constructor(code: ApiErrorCode, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

export function userMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return 'Something went wrong. Please try again.'
  }
  switch (err.code) {
    case 'BACKEND_UNAVAILABLE':
      return 'The backend is not reachable. Is it running?'
    case 'DATABASE_UNAVAILABLE':
      return 'The backend could not connect to MariaDB.'
    case 'LLM_FAILED':
      return 'Search worked, but the answer could not be generated.'
    case 'BAD_REQUEST':
      return err.message || 'The request was invalid.'
    default:
      return err.message || 'Something went wrong. Please try again.'
  }
}