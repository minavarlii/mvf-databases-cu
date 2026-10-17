import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CheckIcon, CopyIcon } from './icons'
import { filterLines } from './sqlFilters'

type TokenKind = 'keyword' | 'function' | 'string' | 'number' | 'param' | 'comment' | 'plain'

const KEYWORDS = new Set(
  `SELECT FROM WHERE AND OR NOT JOIN LEFT RIGHT INNER OUTER CROSS ON AS ORDER BY GROUP HAVING LIMIT OFFSET
   ASC DESC IN IS NULL LIKE BETWEEN DISTINCT UNION ALL WITH CASE WHEN THEN ELSE END INSERT INTO VALUES
   UPDATE SET DELETE CREATE TABLE INDEX VECTOR USING EXISTS TRUE FALSE`.split(/\s+/),
)

const TOKEN = /('(?:[^'\\]|\\.|'')*'?)|(--[^\n]*)|(\?|(?<![\w:]):[A-Za-z_]\w*)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/g

function tokenize(sql: string): { kind: TokenKind; text: string }[] {
  const tokens: { kind: TokenKind; text: string }[] = []
  let last = 0
  for (const m of sql.matchAll(TOKEN)) {
    if (m.index > last) tokens.push({ kind: 'plain', text: sql.slice(last, m.index) })
    const [text, str, comment, param, num, word] = m
    let kind: TokenKind = 'plain'
    if (str) kind = 'string'
    else if (comment) kind = 'comment'
    else if (param) kind = 'param'
    else if (num) kind = 'number'
    else if (word) {
      const next = sql[m.index + text.length]
      if (KEYWORDS.has(word.toUpperCase())) kind = 'keyword'
      else if (next === '(') kind = 'function'
    }
    tokens.push({ kind, text })
    last = m.index + text.length
  }
  if (last < sql.length) tokens.push({ kind: 'plain', text: sql.slice(last) })
  return tokens
}

function highlightLines(sql: string): ReactNode[][] {
  const lines: ReactNode[][] = [[]]
  let key = 0
  for (const { kind, text } of tokenize(sql)) {
    text.split('\n').forEach((part, i) => {
      if (i > 0) lines.push([])
      if (!part) return
      lines[lines.length - 1].push(
        kind === 'plain' ? part : (
          <span key={key++} className={`sql-${kind}`}>
            {part}
          </span>
        ),
      )
    })
  }
  return lines
}

type CopyState = 'idle' | 'copied' | 'failed'

export function SqlBlock({ sql, markFilters }: { sql: string; markFilters: boolean }) {
  const [copy, setCopy] = useState<CopyState>('idle')
  const titleId = useId()
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  async function handleCopy() {
    let next: CopyState = 'copied'
    try {
      await navigator.clipboard.writeText(sql)
    } catch {
      next = 'failed'
    }
    setCopy(next)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopy('idle'), 2000)
  }

  // The backend's SQL constants start and end with a newline.
  const code = sql.replace(/^\s*\n/, '').replace(/\s+$/, '')
  const lines = highlightLines(code)
  const marked = markFilters ? filterLines(code) : new Set<number>()

  return (
    <div className="sql">
      <div className="sql-head">
        <div>
          <h3 id={titleId} className="sql-title">
            Executed SQL
          </h3>
          <p className="sql-caption">
            The exact query MariaDB ran. Each placeholder (? or :name) is a value sent separately.
            {marked.size > 0 && (
              <>
                {' '}
                <span className="sql-legend">Highlighted lines</span> come from your filters: vector search and SQL
                filtering in one query.
              </>
            )}
          </p>
        </div>
        <button type="button" className="btn-soft sql-copy" onClick={handleCopy}>
          {copy === 'copied' ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
          {copy === 'copied' ? 'Copied' : copy === 'failed' ? 'Copy failed' : 'Copy'}
          <span className="sr-only"> SQL</span>
        </button>
        <span className="sr-only" role="status">
          {copy === 'copied' ? 'SQL copied to clipboard' : copy === 'failed' ? 'Could not copy the SQL' : ''}
        </span>
      </div>
      <pre className="sql-code" tabIndex={0} aria-labelledby={titleId}>
        <code>
          {lines.map((parts, i) => (
            <span key={i} className={marked.has(i) ? 'sql-line is-filter' : 'sql-line'}>
              {parts.length ? parts : ' '}
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}
