import { useEffect, useMemo, useRef } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Radio } from 'lucide-react'
import { useJobTranscript } from '../hooks/useJobTranscript'
import { eventTypeLabel, relativeTimeRu, statusLabel } from '../lib/uiCopy'

interface JobChatPanelProps {
  jobId: string | null
  enabled?: boolean
  /** WebSocket caption from voice session — shown while agent thinks / speaks. */
  liveCaption?: string | null
  pollMs?: number
}

const LIVE_STATUSES = new Set(['running', 'planning', 'approved', 'queued'])

const IDLE_CAPTION = 'Коснись кнопки — говори'

function dedupeEvents<T extends { text?: string | null }>(events: T[]): T[] {
  const result: T[] = []
  let lastText = ''
  for (const event of events) {
    const text = event.text?.trim()
    if (!text || text === lastText) continue
    lastText = text
    result.push(event)
  }
  return result
}

function isLiveCaption(caption?: string | null): caption is string {
  if (!caption) return false
  const trimmed = caption.trim()
  if (!trimmed || trimmed === IDLE_CAPTION) return false
  return true
}

export function JobChatPanel({
  jobId,
  enabled = true,
  liveCaption = null,
  pollMs,
}: JobChatPanelProps) {
  const reducedMotion = useReducedMotion()
  const { snapshot, error } = useJobTranscript(jobId, enabled, pollMs)
  const scrollerRef = useRef<HTMLDivElement | null>(null)

  const rawEvents = snapshot?.events.filter((event) => event.text) ?? []
  const events = useMemo(() => dedupeEvents(rawEvents), [snapshot?.events])

  const status = snapshot?.status ?? ''
  const isLive = LIVE_STATUSES.has(status)
  const terminal = ['succeeded', 'completed', 'accepted', 'failed', 'cancelled', 'rejected', 'blocked']
    .includes(status)

  const streamTail = snapshot?.latestText?.trim() || null
  const voiceTail = isLiveCaption(liveCaption) ? liveCaption.trim() : null
  const lastLogged = events.at(-1)?.text?.trim() ?? ''
  const tailCandidate = streamTail || voiceTail
  const tailText = tailCandidate && tailCandidate !== lastLogged ? tailCandidate : null

  useEffect(() => {
    const node = scrollerRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [events.length, tailText])

  const showPanel = Boolean(jobId) || isLiveCaption(liveCaption)

  if (!showPanel) {
    return (
      <section className="job-chat voice-live-feed" aria-label="Прямой эфир">
        <header className="job-chat-header">
          <p className="eyebrow">
            <Radio size={13} aria-hidden="true" /> Прямой эфир
          </p>
        </header>
        <p className="muted-hint">
          Отправьте запрос — здесь появятся ответы и ход мыслей агента.
        </p>
      </section>
    )
  }

  return (
    <motion.section
      className="job-chat voice-live-feed"
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      aria-live="polite"
      aria-label="Прямой эфир агента"
    >
      <header className="job-chat-header">
        <p className="eyebrow">
          <Radio size={13} aria-hidden="true" /> Прямой эфир
          {isLive && (
            <span className="live-badge is-hot">
              <i className="live-pulse" aria-hidden="true" />
              LIVE
            </span>
          )}
        </p>
        {snapshot && (
          <span className={`status-pill status-${snapshot.status}`}>
            {statusLabel(snapshot.status)}
          </span>
        )}
      </header>

      {error && <div className="inline-error" role="alert">{error}</div>}

      {events.length || tailText ? (
        <div className="job-chat-log" ref={scrollerRef}>
          {events.map((event) => (
            <article className="job-chat-message" key={event.id}>
              <p>{event.text}</p>
              <small>
                {eventTypeLabel(event.eventType)}
                {' · '}
                {relativeTimeRu(event.createdAt)}
              </small>
            </article>
          ))}
          {tailText && isLive && (
            <article className="job-chat-message is-streaming" aria-label="Сейчас">
              <p>{tailText}</p>
              <small>
                {streamTail ? eventTypeLabel('run.progress') : 'Сейчас'}
                {' · '}
                эфир
              </small>
            </article>
          )}
        </div>
      ) : (
        <p className="muted-hint">
          {terminal
            ? 'Агент завершил без текстовых событий.'
            : 'Эфир начнётся, когда агент начнёт отвечать.'}
        </p>
      )}
    </motion.section>
  )
}
