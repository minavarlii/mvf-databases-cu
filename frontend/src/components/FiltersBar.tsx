import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { ArticleTitle, Category } from '../api'
import { ArticlePicker } from './ArticlePicker'
import type { ArticlesLoad } from './ArticlePicker'
import { checkFilters, NO_FILTERS, ONE_FILTER_NOTE } from './filters'
import type { FilterDraft, FilterKey } from './filters'
import { ChevronDownIcon, CrossIcon, SearchIcon, SlidersIcon, SpinnerIcon } from './icons'

interface Props {
  draft: FilterDraft
  onChange: (draft: FilterDraft) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  apply: {
    label: string
    onApply: () => void
    questionEmpty: boolean
    loading: boolean
  }
}

type Load = { status: 'loading' } | { status: 'ok'; categories: Category[] } | { status: 'error' }

// Module-level, so StrictMode's double effect still fetches once per page load.
let categoriesRequest: Promise<Category[]> | null = null
const loadCategories = () => (categoriesRequest ??= api.categories())
// All pages of /api/articles, fetched once and filtered client-side by the picker.
let articlesRequest: Promise<ArticleTitle[]> | null = null
const loadArticles = () => (articlesRequest ??= api.articles())

export function FiltersBar({ draft, onChange, open, onOpenChange, apply }: Props) {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [articles, setArticles] = useState<ArticlesLoad>({ status: 'loading' })
  const toggleRef = useRef<HTMLButtonElement>(null)
  const { errors, active } = checkFilters(draft)
  const invalid = Object.keys(errors).length

  useEffect(() => {
    let live = true
    loadCategories().then(
      (categories) => live && setLoad({ status: 'ok', categories }),
      () => live && setLoad({ status: 'error' }),
    )
    loadArticles().then(
      (list) => live && setArticles({ status: 'ok', articles: list }),
      () => live && setArticles({ status: 'error' }),
    )
    return () => {
      live = false
    }
  }, [])

  const set = (key: FilterKey, value: string) => onChange({ ...draft, [key]: value })

  // The clicked pill disappears, so focus goes back to the toggle.
  function remove(key?: FilterKey) {
    onChange(key ? { ...draft, [key]: '' } : NO_FILTERS)
    toggleRef.current?.focus()
  }

  const hasValues = Object.values(draft).some((v) => v.trim())

  const supported = api.capabilities.filters
  // Setting one disables the other; if both are somehow set, neither is locked so either can be cleared.
  const lockCategory = Boolean(draft.linkedFrom) && !draft.category
  const lockLinked = Boolean(draft.category) && !draft.linkedFrom

  return (
    <section className={open ? 'card filters is-open' : 'card filters'} aria-label="Search filters">
      <div className="filters-bar">
        <button
          ref={toggleRef}
          type="button"
          className="filters-toggle"
          aria-expanded={open}
          aria-controls="filter-fields"
          onClick={() => onOpenChange(!open)}
        >
          <span className="filters-icon">
            <SlidersIcon size={16} />
          </span>
          <span className="filters-name">Filters</span>
          {!hasValues && <span className="filters-optional">· optional</span>}
          {active.length > 0 && (
            <span className="mono filters-count">
              {active.length}
              <span className="sr-only"> active</span>
            </span>
          )}
          {!open && invalid > 0 && (
            <span className="filters-invalid">
              {invalid} invalid<span className="sr-only">, open to fix</span>
            </span>
          )}
          <ChevronDownIcon size={15} />
        </button>

        {hasValues && (
          <div className="filter-pills">
            {!open && active.map((f) => (
              <span key={f.key} className="filter-pill">
                {f.label}
                <button type="button" aria-label={`Remove filter: ${f.label}`} onClick={() => remove(f.key)}>
                  <CrossIcon size={12} />
                </button>
              </span>
            ))}
            <button type="button" className="filters-clear" onClick={() => remove()}>
              Clear all
            </button>
          </div>
        )}
      </div>

      <div id="filter-fields" className="filters-fields" hidden={!open}>
        <div className="field">
          <label htmlFor="f-category">Category</label>
          <select
            id="f-category"
            value={draft.category}
            disabled={load.status !== 'ok' || !supported.category || lockCategory}
            aria-describedby={
              lockCategory ? 'f-one-filter' : load.status === 'error' ? 'f-category-note' : undefined
            }
            onChange={(e) => set('category', e.target.value)}
          >
            <option value="">{load.status === 'loading' ? 'Loading…' : 'All categories'}</option>
            {load.status === 'ok' &&
              load.categories.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.article_count.toLocaleString('en-US')})
                </option>
              ))}
          </select>
          {load.status === 'error' && (
            <p id="f-category-note" className="field-note">
              Categories couldn’t be loaded.
            </p>
          )}
        </div>

        <ArticlePicker
          id="f-linked"
          load={articles}
          value={draft.linkedFrom}
          onChange={(title) => set('linkedFrom', title)}
          disabled={!supported.source_title || lockLinked}
          describedBy={
            lockLinked ? 'f-one-filter' : errors.linkedFrom ? 'f-linked-error' : articles.status === 'error' ? 'f-linked-note' : undefined
          }
        />

        {(draft.category || draft.linkedFrom) && !errors.linkedFrom && (
          <p id="f-one-filter" className="field-note filters-span">
            {ONE_FILTER_NOTE}.
          </p>
        )}
        {errors.linkedFrom && (
          <p id="f-linked-error" className="field-error filters-span">
            {errors.linkedFrom}
          </p>
        )}
        {articles.status === 'error' && (
          <p id="f-linked-note" className="field-note filters-span">
            Articles couldn’t be loaded.
          </p>
        )}

        <div className="filters-apply">
          <button
            type="button"
            className="btn-soft filters-apply-btn"
            disabled={apply.loading || apply.questionEmpty || invalid > 0}
            aria-describedby={apply.questionEmpty ? 'f-apply-hint' : undefined}
            onClick={apply.onApply}
          >
            {apply.loading ? (
              <>
                Searching… <SpinnerIcon size={15} />
              </>
            ) : (
              <>
                <SearchIcon size={15} /> {apply.label}
              </>
            )}
          </button>
          {apply.questionEmpty && (
            <p id="f-apply-hint" className="field-note">
              Type a question first
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
