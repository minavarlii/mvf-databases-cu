import type { ArticleTitle, SearchFilters } from '../api'

export interface FilterDraft {
  category: string
  linkedFrom: string // source article title
}

export type FilterKey = keyof FilterDraft

export const NO_FILTERS: FilterDraft = { category: '', linkedFrom: '' }

// Category and linked search are separate endpoints, so only one can run at a time.
export const ONE_FILTER_NOTE = 'One filter at a time: category or linked article'

export type SearchKind = 'vector' | 'category' | 'linked'

interface CheckedFilters {
  filters: SearchFilters
  errors: Partial<Record<FilterKey, string>>
  active: { key: FilterKey; label: string }[]
}

export const searchKind = (f: SearchFilters | undefined): SearchKind =>
  f?.source_title ? 'linked' : f?.category ? 'category' : 'vector'

export function filterLabels(f: SearchFilters): string[] {
  const labels: string[] = []
  if (f.category) labels.push(`Category: ${f.category}`)
  if (f.source_title) labels.push(`Linked from: ${f.source_title}`)
  return labels
}

export function checkFilters(draft: FilterDraft): CheckedFilters {
  const filters: SearchFilters = {}
  const errors: CheckedFilters['errors'] = {}
  const active: CheckedFilters['active'] = []

  // The UI disables the other field, so this only catches a draft set some other way; never drop one silently.
  if (draft.category && draft.linkedFrom) {
    errors.linkedFrom = `${ONE_FILTER_NOTE}.`
    return { filters, errors, active }
  }

  if (draft.category) {
    filters.category = draft.category
    active.push({ key: 'category', label: draft.category })
  }

  if (draft.linkedFrom) {
    filters.source_title = draft.linkedFrom
    active.push({ key: 'linkedFrom', label: `Linked from ${draft.linkedFrom}` })
  }

  return { filters, errors, active }
}

export const filterCount = (f: SearchFilters | undefined) => (f ? Object.keys(f).length : 0)

export const sameFilters = (a: SearchFilters, b: SearchFilters) =>
  a.category === b.category && a.source_title === b.source_title

// Case-insensitive substring match for the article picker; the full list is already in memory.
export function matchArticles(articles: ArticleTitle[], text: string): ArticleTitle[] {
  const q = text.trim().toLowerCase()
  return q ? articles.filter((a) => a.title.toLowerCase().includes(q)) : articles
}
