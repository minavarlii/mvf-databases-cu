import { useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { ArticleTitle } from '../api'
import { matchArticles } from './filters'
import { CrossIcon } from './icons'

export type ArticlesLoad = { status: 'loading' } | { status: 'ok'; articles: ArticleTitle[] } | { status: 'error' }

interface Props {
  id: string
  load: ArticlesLoad
  value: string // selected title, '' for none
  onChange: (title: string) => void
  disabled: boolean
  describedBy?: string
}

// Enough to scroll through; the rest are reached by typing.
const MAX_SHOWN = 60

// ARIA 1.2 combobox: focus stays in the input, aria-activedescendant points at the active option.
// The list is a grid child spanning both filter columns, so it's never clipped by the scrolling column.
export function ArticlePicker({ id, load, value, onChange, disabled, describedBy }: Props) {
  const [text, setText] = useState(value)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  // Follow outside changes (pill removed, Clear all) during render, without an effect.
  const [shownValue, setShownValue] = useState(value)
  if (shownValue !== value) {
    setShownValue(value)
    setText(value)
  }

  const articles = load.status === 'ok' ? load.articles : []
  const matches = matchArticles(articles, text === value ? '' : text)
  const shown = matches.slice(0, MAX_SHOWN)
  const expanded = open && !disabled && load.status === 'ok'
  const optionId = (i: number) => `${listId}-${i}`

  function choose(a: ArticleTitle) {
    onChange(a.title)
    setText(a.title)
    setOpen(false)
    setActive(-1)
  }

  function edit(next: string) {
    setText(next)
    setOpen(true)
    setActive(next.trim() ? 0 : -1)
    if (!next.trim() && value) onChange('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!expanded) {
        setOpen(true)
        setActive(e.key === 'ArrowDown' ? 0 : shown.length - 1)
        return
      }
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((i) => (shown.length ? (i + step + shown.length) % shown.length : -1))
    } else if (e.key === 'Enter' && expanded && shown[active]) {
      e.preventDefault()
      choose(shown[active])
    } else if (e.key === 'Escape') {
      if (expanded) {
        e.preventDefault()
        setOpen(false)
      } else if (text !== value) {
        setText(value)
      }
    }
  }

  // Typed text that wasn't picked from the list isn't a filter; fall back to the chosen title.
  function onBlur() {
    setOpen(false)
    setActive(-1)
    if (text !== value) setText(value)
  }

  function clear() {
    onChange('')
    setText('')
    setOpen(true)
    inputRef.current?.focus()
  }

  const placeholder =
    load.status === 'loading' ? 'Loading articles…' : load.status === 'error' ? 'Not available' : 'Any article'

  return (
    <>
      <div className="field picker">
        <label htmlFor={id}>Linked from article</label>
        <div className="picker-box">
          <input
            ref={inputRef}
            id={id}
            type="text"
            role="combobox"
            autoComplete="off"
            spellCheck={false}
            placeholder={placeholder}
            value={text}
            disabled={disabled || load.status !== 'ok'}
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={expanded && shown[active] ? optionId(active) : undefined}
            aria-describedby={describedBy}
            onChange={(e) => edit(e.target.value)}
            onFocus={() => setOpen(true)}
            onClick={() => setOpen(true)}
            onBlur={onBlur}
            onKeyDown={onKeyDown}
          />
          {value && !disabled && (
            <button type="button" className="picker-clear" aria-label={`Clear linked article: ${value}`} onClick={clear}>
              <CrossIcon size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="picker-pop" hidden={!expanded}>
        <ul id={listId} role="listbox" aria-label="Articles" className="picker-list">
          {shown.map((a, i) => (
            <li
              key={a.id}
              id={optionId(i)}
              role="option"
              aria-selected={a.title === value}
              className={i === active ? 'picker-option is-active' : 'picker-option'}
              // mousedown, so the input doesn't blur (and close the list) before the click lands
              onMouseDown={(e) => {
                e.preventDefault()
                choose(a)
              }}
              onMouseMove={() => i !== active && setActive(i)}
            >
              {a.title}
            </li>
          ))}
        </ul>
        <p className="picker-meta" role="status">
          {matches.length === 0
            ? 'No article matches.'
            : matches.length > shown.length
              ? `${shown.length} of ${matches.length} articles. Type to narrow down.`
              : `${matches.length} ${matches.length === 1 ? 'article' : 'articles'}`}
        </p>
      </div>
    </>
  )
}
