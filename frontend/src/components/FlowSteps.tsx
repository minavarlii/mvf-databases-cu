import type { ReactElement } from 'react'
import { BookIcon, ChatIcon, CheckIcon, CrossIcon, DatabaseIcon, SparkleIcon, SpinnerIcon, VectorSearchIcon } from './icons'
import type { Tone } from './tones'

type StepState = 'pending' | 'active' | 'done' | 'failed'

export interface StepStatus {
  state: StepState
  note: string
  warn?: boolean
}

export interface FlowStates {
  question: StepStatus
  search: StepStatus
  sources: StepStatus
  llm?: StepStatus // left out for filtered searches, which get no answer
  details: StepStatus
}

const STEPS: { key: keyof FlowStates; label: string; tone: Tone; icon: () => ReactElement }[] = [
  { key: 'question', label: 'Question', tone: 'lav', icon: () => <ChatIcon /> },
  { key: 'search', label: 'MariaDB vector search', tone: 'sky', icon: () => <VectorSearchIcon /> },
  { key: 'sources', label: 'Retrieved sources', tone: 'peach', icon: () => <BookIcon /> },
  { key: 'llm', label: 'LLM answer', tone: 'butter', icon: () => <SparkleIcon /> },
  { key: 'details', label: 'MariaDB details', tone: 'mint', icon: () => <DatabaseIcon /> },
]

const STATE_TEXT: Record<StepState, string> = {
  pending: 'pending',
  active: 'in progress',
  done: 'done',
  failed: 'failed',
}

export function FlowSteps({ states }: { states: FlowStates }) {
  const steps = STEPS.flatMap((s) => {
    const status = states[s.key]
    return status ? [{ ...s, status }] : []
  })
  return (
    <section className="card flow-card" aria-label="Progress">
      <ol className="flow">
        {steps.map(({ key, label, tone, icon, status }, i) => {
          const { state, note, warn } = status
          const next = steps[i + 1]?.status.state ?? null
          const linked = state === 'done' && next !== null && next !== 'pending'
          return (
            <li key={key} className={`flow-step is-${state}`}>
              <span className="sr-only">
                {label}: {STATE_TEXT[state]}, {note}
              </span>
              <div className="flow-track" aria-hidden="true">
                <span className="flow-icon-wrap">
                  <span className={`flow-icon tone-${tone}`}>{icon()}</span>
                  {state === 'active' && <SpinnerIcon size={56} className="flow-ring" />}
                  {state === 'done' && (
                    <span className="flow-badge badge-done">
                      <CheckIcon size={11} />
                    </span>
                  )}
                  {state === 'failed' && (
                    <span className="flow-badge badge-failed">
                      <CrossIcon size={11} />
                    </span>
                  )}
                </span>
                {next !== null && <span className={linked ? 'flow-line is-linked' : 'flow-line'} />}
              </div>
              <div className="flow-text" aria-hidden="true">
                <span className="flow-label">{label}</span>
                <span className={warn ? 'mono flow-note is-warn' : 'mono flow-note'}>{note}</span>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
