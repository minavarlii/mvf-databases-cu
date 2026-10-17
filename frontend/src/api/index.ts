import { realApi } from './client'
import { mockApi } from './mock'
import type { ApiClient } from './types'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
export const api: ApiClient = USE_MOCK ? mockApi : realApi

export type * from './types'
export { ApiError, userMessage } from './errors'
export { VECTOR_INDEX } from './client'