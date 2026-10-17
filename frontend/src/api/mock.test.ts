import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './errors'
import { mockApi } from './mock'
import type { SearchRequest } from './types'

// The mock waits like a network would; fake timers keep the tests instant.
beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

async function settle<T>(promise: Promise<T>): Promise<T> {
  const result = promise.then(
    (value) => ({ value }),
    (error: unknown) => ({ error }),
  )
  await vi.runAllTimersAsync()
  const r = await result
  if ('error' in r) throw r.error
  return r.value
}

const search = (req: SearchRequest) => settle(mockApi.search(req))

describe('mockApi linked search', () => {
  it('returns only chunks of articles linked from the source, with the backend’s linked SQL and plan', async () => {
    const res = await search({ question: 'What is overfitting?', filters: { source_title: 'Overfitting' } })

    expect(new Set(res.chunks.map((c) => c.article_title))).toEqual(
      new Set(['Machine learning', 'Cross-validation (statistics)', 'Bias–variance tradeoff']),
    )
    expect(res.chunks.map((c) => c.distance)).toEqual([...res.chunks.map((c) => c.distance)].sort((a, b) => a - b))
    expect(res.details.sql).toContain('FROM article_links AS al')
    expect(res.details.sql).toContain('WHERE source.title = :source_title')
    expect(res.details.query_plan.map((r) => [r.table, r.key])).toEqual([
      ['source', 'ix_articles_title'],
      ['al', 'PRIMARY'],
      ['target', 'PRIMARY'],
      ['c', 'ix_chunks_article_id'],
    ])
    expect(res.details.vector_index_used).toBe(false)
  })

  it('returns nothing for an article with no links into the mock chunks', async () => {
    const res = await search({ question: 'q', filters: { source_title: 'Machine learning in earth sciences' } })
    expect(res.chunks).toEqual([])
  })

  it('rejects category and linked together, like the real client', async () => {
    await expect(
      search({ question: 'q', filters: { category: 'Machine learning', source_title: 'Overfitting' } }),
    ).rejects.toMatchObject({ code: 'BAD_REQUEST' })
  })

  it('fails the filtered compare side on !failhybrid and names it linked', async () => {
    const err = await search({ question: 'q !failhybrid', filters: { source_title: 'Overfitting' } }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ message: 'Mock: linked search failed' })
  })
})

describe('mockApi', () => {
  it('keeps category search on the vector index', async () => {
    const res = await search({ question: 'q', filters: { category: 'Model selection' } })
    expect(res.chunks.map((c) => c.article_title)).toEqual(['Cross-validation (statistics)', 'Bias–variance tradeoff'])
    expect(res.details.vector_index_used).toBe(true)
    expect(res.details.sql).toContain('WHERE cat.name = :category')
  })

  it('lists articles for the picker, including every linked source', async () => {
    vi.stubGlobal('window', { location: { search: '' } })
    try {
      const titles = (await settle(mockApi.articles())).map((a) => a.title)
      expect(titles).toEqual([...titles].sort((a, b) => a.localeCompare(b)))
      for (const t of ['Machine learning', 'Overfitting', 'Bias–variance tradeoff', 'Cross-validation (statistics)']) {
        expect(titles).toContain(t)
      }
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
