import { useEffect, useRef } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { MessageSquare } from 'lucide-react'
import { useJobTranscript } from '../hooks/useJobTranscript'
import { eventTypeLabel, relativeTimeRu, statusLabel } from '../lib/uiCopy'

interface JobChatPanelProps {
  jobId: string | null
  enabled?: boolean
}

export function JobChatPanel({ jobId, enabled = true }: JobChatPanelProps) {
  const reducedMotion = useReducedMotion()
  const { snapshot, error } = useJobTranscript(jobId, enabled)
  const scrollerRef = useRef<HTMLDivElement | null>(null)

  const events = snapshot?.events.filter((event) => event.text) ?? []

  useEffect(() => {
    const node = scrollerRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [events.length, snapshot?.latestText])

  if (!jobId) return null

  const terminal = ['succeeded', 'completed', 'accepted', 'failed', 'cancelled', 'rejected', 'blocked']
    .includes(snapshot?.status ?? '')

  return (
    <motion.section
      className="job-chat"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      aria-live="polite"
    >
      <header className="job-chat-header">
        <p className="eyebrow">
          <MessageSquare size={13} aria-hidden="true" /> Ход задачи
        </p>
        {snapshot && (
          <span className={`status-pill status-${snapshot.status}`}>
            {statusLabel(snapshot.status)}
          </span>
        )}
      </header>
      {error && <div className="inline-error" role="alert">{error}</div>}
      {events.length ? (
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
        </div>
      ) : (
        <p className="muted-hint">
          {terminal
            ? 'Транскрипт пуст — агент завершил без текстовых событий.'
            : 'Транскрипт появится, когда агент начнёт отвечать.'}
        </p>
      )}
    </motion.section>
  )
}
