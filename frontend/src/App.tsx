import { useEffect, useSyncExternalStore } from 'react'
import { USE_MOCK } from './api'
import { ChartIcon, DatabaseIcon, SearchIcon, WarningIcon } from './components/icons'
import { StatsStrip } from './components/StatsStrip'
import AskPage from './pages/AskPage'
import EvalPage from './pages/EvalPage'

type Page = 'ask' | 'eval'

const subscribe = (onChange: () => void) => {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

const currentPage = (): Page =>
  window.location.hash === '#/eval' ? 'eval' : 'ask'

const PAGES = [
  {
    page: 'ask',
    href: '#/',
    label: 'Ask',
    icon: <SearchIcon size={16} />,
  },
  {
    page: 'eval',
    href: '#/eval',
    label: 'Evaluation',
    icon: <ChartIcon size={16} />,
  },
] as const

const TAGLINES: Record<Page, string> = {
  ask:
    'MVF finds the closest Wikipedia passages with native vector search, then an LLM answers from them.',
  eval:
    'How well and how fast MariaDB vector search retrieves the right articles, from the repo’s benchmark runs.',
}

export default function App() {
  const page = useSyncExternalStore(subscribe, currentPage)

  useEffect(() => {
    document.title =
      page === 'eval'
        ? 'Evaluation · MVF'
        : 'MVF · MariaDB Vector Finder'
  }, [page])

  return (
    <div className={USE_MOCK ? 'app is-mock' : 'app'}>
      <div className="app-blobs" aria-hidden="true" />

      <header className="topbar">
        <div className="brand">
          <span className="logo">
            <DatabaseIcon size={22} />
          </span>

          <div className="brand-text">
            <h1>MVF</h1>
            <span className="brand-subtitle">
              MariaDB Vector Finder
            </span>
          </div>

          {USE_MOCK && (
            <span
              className="mono badge-mock"
              title="VITE_USE_MOCK=true: answers, search results and stats are canned, not from the backend"
            >
              <WarningIcon size={14} />
              MOCK DATA
            </span>
          )}

          <nav className="page-tabs" aria-label="Pages">
            {PAGES.map((p) => (
              <a
                key={p.page}
                href={p.href}
                className="page-tab"
                aria-current={
                  page === p.page ? 'page' : undefined
                }
              >
                {p.icon}
                {p.label}
              </a>
            ))}
          </nav>
        </div>

        <p className="tagline">{TAGLINES[page]}</p>

        <StatsStrip />
      </header>

      <AskPage hidden={page !== 'ask'} />

      {page === 'eval' && <EvalPage />}
    </div>
  )
}
