import { useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import {
  Cloud,
  Loader2,
  MessageSquare,
  Monitor,
  Send,
} from 'lucide-react'
import type { AgentSlot, WorkerNode } from '../types/api'
import { useJobTranscript } from '../hooks/useJobTranscript'
import { feedback } from '../lib/feedback'
import { eventTypeLabel, relativeTimeRu, statusLabel } from '../lib/uiCopy'

type PromptMode = 'ask' | 'plan' | 'do'

const MODE_LABELS: Record<PromptMode, string> = {
  ask: 'Спросить',
  plan: 'План',
  do: 'Сделать',
}

interface UpdateAgentInput {
  runtime?: string
  localPath?: string | null
  preferredWorkerId?: string | null
  makeActive?: boolean
}

interface SubmitPromptInput {
  prompt: string
  mode?: PromptMode
  slotId?: string
}

interface SubmitPromptResult {
  job: { id: string }
  enqueued: boolean
  reason?: string
}

interface AgentControlPanelProps {
  slots: AgentSlot[]
  workers: WorkerNode[]
  role: string
  onUpdateAgent: (slotId: string, input: UpdateAgentInput) => Promise<void>
  onSubmitPrompt: (input: SubmitPromptInput) => Promise<SubmitPromptResult>
  onJobDispatched?: (jobId: string, runtime: string | null | undefined) => void
}

function canUseMode(role: string, mode: PromptMode): boolean {
  const normalized = role.toLowerCase()
  if (mode === 'ask') return normalized !== 'none' && normalized !== ''
  return normalized === 'owner' || normalized === 'operator' || normalized === 'admin'
}

export function AgentControlPanel({
  slots,
  workers,
  role,
  onUpdateAgent,
  onSubmitPrompt,
  onJobDispatched,
}: AgentControlPanelProps) {
  const activeSlot = slots.find((slot) => slot.active) ?? slots[0] ?? null
  const [localPath, setLocalPath] = useState(activeSlot?.localPath ?? '')
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<PromptMode>('ask')
  const [runtimeBusy, setRuntimeBusy] = useState(false)
  const [promptBusy, setPromptBusy] = useState(false)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [promptError, setPromptError] = useState<string | null>(null)

  useEffect(() => {
    setLocalPath(activeSlot?.localPath ?? '')
    setRuntimeError(null)
  }, [activeSlot?.id, activeSlot?.localPath])

  useEffect(() => {
    if (!canUseMode(role, mode)) setMode('ask')
  }, [role, mode])

  if (!activeSlot) return null

  const isWindows = activeSlot.runtime === 'windows'
  const pathDirty = (localPath.trim() || '') !== (activeSlot.localPath ?? '')
  const canPlan = canUseMode(role, 'plan')
  const canDo = canUseMode(role, 'do')

  const switchRuntime = (runtime: 'cloud' | 'windows') => {
    if (runtime === activeSlot.runtime || runtimeBusy) return
    if (runtime === 'windows' && !localPath.trim()) {
      setRuntimeError('Укажите путь к репозиторию на Windows-машине')
      return
    }
    setRuntimeBusy(true)
    setRuntimeError(null)
    feedback('tap')
    void onUpdateAgent(activeSlot.id, {
      runtime,
      localPath: runtime === 'windows' ? localPath.trim() : undefined,
    })
      .then(() => feedback('success'))
      .catch((err: unknown) => {
        feedback('error')
        setRuntimeError(err instanceof Error ? err.message : 'Не удалось переключить режим')
      })
      .finally(() => setRuntimeBusy(false))
  }

  const savePath = () => {
    if (!pathDirty || runtimeBusy) return
    setRuntimeBusy(true)
    setRuntimeError(null)
    feedback('tap')
    void onUpdateAgent(activeSlot.id, { localPath: localPath.trim() })
      .then(() => feedback('success'))
      .catch((err: unknown) => {
        feedback('error')
        setRuntimeError(err instanceof Error ? err.message : 'Не удалось сохранить путь')
      })
      .finally(() => setRuntimeBusy(false))
  }

  const send = () => {
    if (!prompt.trim() || promptBusy) return
    if (!canUseMode(role, mode)) {
      setPromptError('Этот режим недоступен для вашей роли')
      return
    }
    if (isWindows && !activeSlot.localPath && !localPath.trim()) {
      setPromptError('Для Windows нужен путь к репозиторию')
      return
    }
    setPromptBusy(true)
    setPromptError(null)
    feedback('tap')
    void onSubmitPrompt({ prompt: prompt.trim(), mode, slotId: activeSlot.id })
      .then((result) => {
        if (!result.enqueued) {
          feedback('warning')
          setPromptError(result.reason || 'Запрос заблокирован политикой')
          return
        }
        feedback('success')
        setPrompt('')
        onJobDispatched?.(result.job.id, activeSlot.runtime)
      })
      .catch((err: unknown) => {
        feedback('error')
        setPromptError(err instanceof Error ? err.message : 'Не удалось отправить запрос')
      })
      .finally(() => setPromptBusy(false))
  }

  return (
    <motion.section
      className="agent-control"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <header className="agent-control-header">
        <p className="eyebrow">Управление</p>
        <h2>{activeSlot.label}</h2>
        <p className="muted-hint">
          Агент видит очередь, approve и активный runtime — пишите как в чате.
        </p>
      </header>

      <div className="runtime-toggle" role="toolbar" aria-label="Режим исполнения">
        <button
          type="button"
          className={!isWindows ? 'selected' : ''}
          aria-pressed={!isWindows}
          disabled={runtimeBusy}
          onClick={() => switchRuntime('cloud')}
        >
          <Cloud size={15} aria-hidden="true" /> Cloud
        </button>
        <button
          type="button"
          className={isWindows ? 'selected' : ''}
          aria-pressed={isWindows}
          disabled={runtimeBusy}
          onClick={() => switchRuntime('windows')}
        >
          <Monitor size={15} aria-hidden="true" /> Windows
        </button>
      </div>

      <label className="agent-path-field">
        <span>Путь к репозиторию (Windows)</span>
        <div className="agent-path-row">
          <input
            value={localPath}
            onChange={(event) => setLocalPath(event.target.value)}
            placeholder="C:\\Work\\repo"
            autoComplete="off"
            disabled={runtimeBusy}
          />
          <button type="button" disabled={!pathDirty || runtimeBusy} onClick={savePath}>
            {runtimeBusy ? <Loader2 size={15} className="spin-icon" aria-hidden="true" /> : 'Сохранить'}
          </button>
        </div>
      </label>
      {workers.length > 0 ? (
        <p className="muted-hint">
          Онлайн Windows-воркеры: {workers.map((worker) => worker.hostname).join(', ')}
        </p>
      ) : (
        <p className="muted-hint">Windows-воркеры офлайн — Cloud работает как обычно.</p>
      )}
      {runtimeError && <div className="inline-error" role="alert">{runtimeError}</div>}

      <div className="prompt-mode-row" role="toolbar" aria-label="Режим запроса">
        {(['ask', 'plan', 'do'] as const).map((item) => {
          const allowed = item === 'ask' ? true : item === 'plan' ? canPlan : canDo
          return (
            <button
              key={item}
              type="button"
              className={mode === item ? 'selected' : ''}
              aria-pressed={mode === item}
              disabled={!allowed}
              title={!allowed ? 'Нужна роль оператора или владельца' : undefined}
              onClick={() => setMode(item)}
            >
              {MODE_LABELS[item]}
            </button>
          )
        })}
      </div>

      <form
        className="prompt-form"
        onSubmit={(event) => {
          event.preventDefault()
          send()
        }}
      >
        <label htmlFor="agent-prompt">Запрос агенту</label>
        <textarea
          id="agent-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Опишите задачу для агента…"
          rows={3}
          maxLength={8000}
          disabled={promptBusy}
        />
        <button type="submit" disabled={promptBusy || !prompt.trim()}>
          {promptBusy ? <Loader2 size={16} className="spin-icon" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
          {MODE_LABELS[mode]}
        </button>
      </form>
      {promptError && <div className="inline-error" role="alert">{promptError}</div>}
    </motion.section>
  )
}

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
          <MessageSquare size={13} aria-hidden="true" /> Эфир задачи
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
