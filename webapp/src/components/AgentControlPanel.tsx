import { useState } from 'react'
import { motion } from 'motion/react'
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
import { relativeTimeRu, statusLabel } from '../lib/uiCopy'

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

  if (!activeSlot) return null

  const isWindows = activeSlot.runtime === 'windows'
  const canDo = role.toLowerCase() === 'owner'
  const pathDirty = (localPath.trim() || '') !== (activeSlot.localPath ?? '')

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
    if (isWindows && !activeSlot.localPath) {
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
      </header>

      <div className="runtime-toggle" role="toolbar" aria-label="Режим исполнения">
        <button
          type="button"
          className={!isWindows ? 'selected' : ''}
          aria-pressed={!isWindows}
          disabled={runtimeBusy}
          onClick={() => switchRuntime('cloud')}
        >
          <Cloud size={15} /> Cloud
        </button>
        <button
          type="button"
          className={isWindows ? 'selected' : ''}
          aria-pressed={isWindows}
          disabled={runtimeBusy}
          onClick={() => switchRuntime('windows')}
        >
          <Monitor size={15} /> Windows
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
            {runtimeBusy ? <Loader2 size={15} className="spin-icon" /> : 'Сохранить'}
          </button>
        </div>
      </label>
      {workers.length > 0 && (
        <p className="muted-hint">
          Онлайн Windows-воркеры: {workers.map((worker) => worker.hostname).join(', ')}
        </p>
      )}
      {runtimeError && <div className="inline-error" role="alert">{runtimeError}</div>}

      <div className="prompt-mode-row" role="toolbar" aria-label="Режим запроса">
        {(['ask', 'plan', 'do'] as const).map((item) => (
          <button
            key={item}
            type="button"
            className={mode === item ? 'selected' : ''}
            aria-pressed={mode === item}
            disabled={item === 'do' && !canDo}
            title={item === 'do' && !canDo ? 'Требуется роль владельца' : undefined}
            onClick={() => setMode(item)}
          >
            {MODE_LABELS[item]}
          </button>
        ))}
      </div>

      <form
        className="prompt-form"
        onSubmit={(event) => {
          event.preventDefault()
          send()
        }}
      >
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Опишите задачу для агента..."
          rows={3}
        />
        <button type="submit" disabled={promptBusy || !prompt.trim()}>
          {promptBusy ? <Loader2 size={16} className="spin-icon" /> : <Send size={16} />}
          Отправить
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
  const { snapshot, error } = useJobTranscript(jobId, enabled)

  if (!jobId) return null

  const events = snapshot?.events.filter((event) => event.text) ?? []

  return (
    <motion.section
      className="job-chat"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <header className="job-chat-header">
        <p className="eyebrow">
          <MessageSquare size={13} /> Эфир задачи
        </p>
        {snapshot && (
          <span className={`status-pill status-${snapshot.status}`}>
            {statusLabel(snapshot.status)}
          </span>
        )}
      </header>
      {error && <div className="inline-error" role="alert">{error}</div>}
      {events.length ? (
        <div className="job-chat-log">
          {events.map((event) => (
            <article className="job-chat-message" key={event.id}>
              <p>{event.text}</p>
              <small>
                {event.eventType}
                {' · '}
                {relativeTimeRu(event.createdAt)}
              </small>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-hint">Транскрипт появится, когда агент начнёт отвечать.</p>
      )}
    </motion.section>
  )
}
