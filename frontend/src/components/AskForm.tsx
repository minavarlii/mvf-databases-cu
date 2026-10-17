import { useLayoutEffect, useRef } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ArrowRightIcon, SpinnerIcon } from './icons'
import type { Tone } from './tones'

const CHIP_TONES: Tone[] = ['lav', 'sky', 'mint']

interface Props {
  value: string
  loading: boolean
  examples: string[]
  onChange: (value: string) => void
  onSubmit: (question: string) => void
  blockedReason?: string | null
  onBlocked?: () => void
}

export function AskForm({ value, loading, examples, onChange, onSubmit, blockedReason, onBlocked }: Props) {
  const canSubmit = value.trim().length > 0 && !loading
  const blocked = Boolean(blockedReason)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${ta.scrollHeight}px`
  }, [value])

  function submit() {
    if (!canSubmit) return
    if (blocked) onBlocked?.()
    else onSubmit(value.trim())
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    submit()
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter' || e.nativeEvent.isComposing) return
    if (!e.shiftKey || e.ctrlKey || e.metaKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <section className="card ask-card" aria-label="Ask a question">
      <form className="ask-form" onSubmit={handleSubmit}>
        <label htmlFor="question" className="ask-label">
          Your question
        </label>
        <textarea
          ref={textareaRef}
          id="question"
          rows={1} // starting height comes from the CSS min-height
          value={value}
          placeholder="e.g. What is transfer learning?"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="ask-row">
          <div className="examples">
            <span className="examples-label">Try:</span>
            {examples.map((q, i) => (
              <button
                key={q}
                type="button"
                className={`chip tone-${CHIP_TONES[i % CHIP_TONES.length]}`}
                disabled={loading}
                onClick={() => {
                  onChange(q)
                  if (blocked) onBlocked?.()
                  else onSubmit(q)
                }}
              >
                {q}
              </button>
            ))}
          </div>
          <div className="ask-submit">
            <span className="ask-note">
              <span className="ask-blocked" id="ask-blocked" role="status">
                {blockedReason}
              </span>
              {!loading && !blocked && <span className="mono hint">Enter to send</span>}
            </span>
            {/* aria-disabled, not disabled: a click must still open the filters with the errors. */}
            <button
              type="submit"
              className="btn-primary"
              disabled={!canSubmit}
              aria-disabled={blocked || undefined}
              aria-describedby={blocked ? 'ask-blocked' : undefined}
            >
              {loading ? (
                <>
                  Searching… <SpinnerIcon size={17} />
                </>
              ) : (
                <>
                  Ask <ArrowRightIcon size={17} />
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}
