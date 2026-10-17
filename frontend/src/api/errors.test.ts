import { describe, expect, it } from 'vitest'
import { ApiError, userMessage } from './errors'
import type { ApiErrorCode } from './types'

// A Record over ApiErrorCode, so adding a code without a case here fails tsc.
const EXPECTED: Record<ApiErrorCode, string> = {
  BACKEND_UNAVAILABLE: 'The backend is not reachable. Is it running?',
  DATABASE_UNAVAILABLE: 'The backend could not connect to MariaDB.',
  LLM_FAILED: 'Search worked, but the answer could not be generated.',
  BAD_REQUEST: 'query: String should have at least 1 character (HTTP 422)',
  UNKNOWN: 'Internal error (HTTP 500)',
}

const DETAIL: Record<ApiErrorCode, string> = {
  BACKEND_UNAVAILABLE: 'Could not reach the backend at http://localhost:8000.',
  DATABASE_UNAVAILABLE: 'Lost connection to MariaDB',
  LLM_FAILED: 'RAG generation is unavailable (HTTP 503)',
  BAD_REQUEST: 'query: String should have at least 1 character (HTTP 422)',
  UNKNOWN: 'Internal error (HTTP 500)',
}

describe('userMessage', () => {
  it.each(Object.keys(EXPECTED) as ApiErrorCode[])('%s', (code) => {
    expect(userMessage(new ApiError(code, DETAIL[code]))).toBe(EXPECTED[code])
  })

  it('falls back to a generic text when a pass-through code has no message', () => {
    expect(userMessage(new ApiError('BAD_REQUEST', ''))).toBe('The request was invalid.')
    expect(userMessage(new ApiError('UNKNOWN', ''))).toBe('Something went wrong. Please try again.')
  })

  it('does not leak messages from errors that are not ApiErrors', () => {
    expect(userMessage(new TypeError('x is undefined'))).toBe('Something went wrong. Please try again.')
    expect(userMessage('boom')).toBe('Something went wrong. Please try again.')
  })
})
