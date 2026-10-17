import { describe, expect, it } from 'vitest'
import { checkFilters, filterLabels, matchArticles, NO_FILTERS, sameFilters, searchKind } from './filters'
import { filterLines } from './sqlFilters'

describe('checkFilters', () => {
  it('turns a category into a hybrid filter', () => {
    expect(checkFilters({ ...NO_FILTERS, category: 'Machine learning' })).toEqual({
      filters: { category: 'Machine learning' },
      errors: {},
      active: [{ key: 'category', label: 'Machine learning' }],
    })
  })

  it('turns a linked article into source_title', () => {
    const { filters, active } = checkFilters({ ...NO_FILTERS, linkedFrom: 'Overfitting' })
    expect(filters).toEqual({ source_title: 'Overfitting' })
    expect(active).toEqual([{ key: 'linkedFrom', label: 'Linked from Overfitting' }])
    expect(searchKind(filters)).toBe('linked')
  })

  it('flags both at once instead of silently sending one', () => {
    const { filters, errors } = checkFilters({ category: 'Machine learning', linkedFrom: 'Overfitting' })
    expect(filters).toEqual({})
    expect(errors.linkedFrom).toMatch(/One filter at a time/)
  })
})

describe('filter helpers', () => {
  it('labels and compares both kinds', () => {
    expect(filterLabels({ category: 'Model selection' })).toEqual(['Category: Model selection'])
    expect(filterLabels({ source_title: 'Overfitting' })).toEqual(['Linked from: Overfitting'])
    expect(sameFilters({ source_title: 'A' }, { source_title: 'A' })).toBe(true)
    expect(sameFilters({ source_title: 'A' }, { category: 'A' })).toBe(false)
    expect(searchKind({})).toBe('vector')
    expect(searchKind({ category: 'X' })).toBe('category')
  })

  it('matches article titles case-insensitively anywhere in the title', () => {
    const articles = [
      { id: 1, title: 'Machine learning' },
      { id: 2, title: 'Leakage (machine learning)' },
      { id: 3, title: 'Overfitting' },
    ]
    expect(matchArticles(articles, '  MACHINE ').map((a) => a.id)).toEqual([1, 2])
    expect(matchArticles(articles, '')).toBe(articles)
    expect(matchArticles(articles, 'zzz')).toEqual([])
  })
})

describe('filterLines', () => {
  const lines = (sql: string) => {
    const all = sql.split('\n')
    return [...filterLines(sql)].map((i) => all[i].trim())
  }

  // LINKED_SEARCH_SQL from backend/app/db/queries/vector.py.
  it('marks the article_links join and the source condition in linked SQL, not the vector ranking', () => {
    const sql = `SELECT
    c.id AS chunk_id,
    target.title AS article_title,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = :source_title
ORDER BY distance ASC
LIMIT :limit`
    expect(lines(sql)).toEqual([
      'FROM article_links AS al',
      'INNER JOIN articles AS source',
      'ON source.id = al.source_article_id',
      'INNER JOIN articles AS target',
      'ON target.id = al.target_article_id',
      'WHERE source.title = :source_title',
    ])
  })

  it('marks the category subquery in hybrid SQL and nothing in plain SQL', () => {
    const hybrid = `    FROM chunks
    WHERE article_id IN (
        SELECT ac.article_id
        FROM article_categories AS ac
        INNER JOIN categories AS cat
            ON cat.id = ac.category_id
        WHERE cat.name = :category
    )
    ORDER BY distance ASC`
    expect(lines(hybrid)).toHaveLength(6)
    expect(lines('SELECT id FROM chunks\nINNER JOIN articles AS a\n    ON a.id = c.article_id')).toEqual([])
  })
})
