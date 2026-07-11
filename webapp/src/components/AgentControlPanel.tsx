import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  CheckCircle2,
  Cloud,
  ImagePlus,
  Loader2,
  MessageSquare,
  Monitor,
  Send,
  Wifi,
  WifiOff,
  X,
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

const MAX_ATTACHMENTS = 8
const MAX_IMAGE_BYTES = 4 * 1024 * 1024
const ACCEPTED_MIME = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'])

interface PromptAttachment {
  id: string
  mimeType: string
  previewUrl: string
  dataUrl: string
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
  images?: Array<{ mimeType: string; data: string }>
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

function normalizeMime(mime: string): string {
  const value = mime.trim().toLowerCase()
  if (value === 'image/jpg') return 'image/jpeg'
  return value
}

async function fileToAttachment(file: File): Promise<PromptAttachment> {
  const mimeType = normalizeMime(file.type || 'image/png')
  if (!ACCEPTED_MIME.has(mimeType)) {
    throw new Error('Нужен PNG, JPEG, WebP или GIF')
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new Error('Картинка больше 4 МБ')
  }
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Не удалось прочитать файл'))
    reader.readAsDataURL(file)
  })
  return {
    id: crypto.randomUUID(),
    mimeType,
    previewUrl: dataUrl,
    dataUrl,
  }
}

type RuntimeFlash = {
  tone: 'ok' | 'warn'
  title: string
  detail: string
}

function workerHostnames(workers: WorkerNode[]): string {
  return workers.map((worker) => worker.hostname).filter(Boolean).join(', ')
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
  const [attachments, setAttachments] = useState<PromptAttachment[]>([])
  const [mode, setMode] = useState<PromptMode>('ask')
  const [runtimeBusy, setRuntimeBusy] = useState(false)
  const [promptBusy, setPromptBusy] = useState(false)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [promptError, setPromptError] = useState<string | null>(null)
  const [flash, setFlash] = useState<RuntimeFlash | null>(null)
  const [pathSaved, setPathSaved] = useState(false)
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pathSavedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    setLocalPath(activeSlot?.localPath ?? '')
    setRuntimeError(null)
  }, [activeSlot?.id, activeSlot?.localPath])

  useEffect(() => {
    if (!canUseMode(role, mode)) setMode('ask')
  }, [role, mode])

  useEffect(() => {
    return () => {
      if (flashTimer.current) clearTimeout(flashTimer.current)
      if (pathSavedTimer.current) clearTimeout(pathSavedTimer.current)
    }
  }, [])

  const addFiles = async (files: FileList | File[]) => {
    const list = Array.from(files)
    if (!list.length) return
    const room = MAX_ATTACHMENTS - attachments.length
    if (room <= 0) {
      setPromptError(`Максимум ${MAX_ATTACHMENTS} скринов за раз`)
      feedback('warning')
      return
    }
    try {
      const next = await Promise.all(list.slice(0, room).map((file) => fileToAttachment(file)))
      setAttachments((prev) => [...prev, ...next].slice(0, MAX_ATTACHMENTS))
      setPromptError(null)
      feedback('select')
    } catch (err: unknown) {
      feedback('error')
      setPromptError(err instanceof Error ? err.message : 'Не удалось добавить картинку')
    }
  }

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((item) => item.id !== id))
    feedback('select')
  }

  if (!activeSlot) return null

  const isWindows = activeSlot.runtime === 'windows'
  const pathDirty = (localPath.trim() || '') !== (activeSlot.localPath ?? '')
  const canPlan = canUseMode(role, 'plan')
  const canDo = canUseMode(role, 'do')
  // Dashboard already returns only heartbeat-live workers.
  const workersLive = workers.length > 0
  const hostLabel = workerHostnames(workers)
  const savedPath = (activeSlot.localPath ?? '').trim()
  const effectivePath = savedPath || localPath.trim()

  const showFlash = (next: RuntimeFlash) => {
    setFlash(next)
    if (flashTimer.current) clearTimeout(flashTimer.current)
    flashTimer.current = setTimeout(() => setFlash(null), 4200)
  }

  const markPathSaved = () => {
    setPathSaved(true)
    if (pathSavedTimer.current) clearTimeout(pathSavedTimer.current)
    pathSavedTimer.current = setTimeout(() => setPathSaved(false), 2200)
  }

  const windowsReadyFlash = (path: string): RuntimeFlash => {
    if (!workersLive) {
      return {
        tone: 'warn',
        title: 'Windows выбран, воркер офлайн',
        detail: 'Путь сохранён. Запустите Windows-воркер — иначе задача не подхватится.',
      }
    }
    return {
      tone: 'ok',
      title: 'Windows подключён',
      detail: `${hostLabel || 'воркер'} · ${path}`,
    }
  }

  const switchRuntime = (runtime: 'cloud' | 'windows') => {
    if (runtime === activeSlot.runtime || runtimeBusy) return
    if (runtime === 'windows' && !localPath.trim()) {
      setRuntimeError('Укажите путь к репозиторию на Windows-машине')
      showFlash({
        tone: 'warn',
        title: 'Сначала укажите путь',
        detail: 'Без локального пути Windows-агент не знает, в какой папке работать.',
      })
      feedback('warning')
      return
    }
    setRuntimeBusy(true)
    setRuntimeError(null)
    feedback('tap')
    void onUpdateAgent(activeSlot.id, {
      runtime,
      localPath: runtime === 'windows' ? localPath.trim() : undefined,
    })
      .then(() => {
        feedback('success')
        if (runtime === 'windows') {
          showFlash(windowsReadyFlash(localPath.trim()))
        } else {
          showFlash({
            tone: 'ok',
            title: 'Cloud активен',
            detail: 'Следующие задачи уйдут в облако Cursor.',
          })
        }
      })
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
    const nextPath = localPath.trim()
    void onUpdateAgent(activeSlot.id, { localPath: nextPath })
      .then(() => {
        feedback('success')
        markPathSaved()
        if (isWindows || nextPath) {
          showFlash(
            isWindows
              ? windowsReadyFlash(nextPath)
              : {
                  tone: 'ok',
                  title: 'Путь сохранён',
                  detail: nextPath
                    ? `${nextPath} — переключите на Windows, чтобы слать туда задачи.`
                    : 'Путь очищен.',
                },
          )
        }
      })
      .catch((err: unknown) => {
        feedback('error')
        setRuntimeError(err instanceof Error ? err.message : 'Не удалось сохранить путь')
      })
      .finally(() => setRuntimeBusy(false))
  }

  const send = () => {
    if ((!prompt.trim() && attachments.length === 0) || promptBusy) return
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
    void onSubmitPrompt({
      prompt: prompt.trim(),
      mode,
      slotId: activeSlot.id,
      images: attachments.map((item) => ({
        mimeType: item.mimeType,
        data: item.dataUrl,
      })),
    })
      .then((result) => {
        if (!result.enqueued) {
          feedback('warning')
          setPromptError(result.reason || 'Запрос заблокирован политикой')
          return
        }
        feedback('success')
        setPrompt('')
        setAttachments([])
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
          Агент видит очередь и approve. Можно прикрепить скрины багов.
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

      <div
        className={`runtime-status ${isWindows ? (workersLive && effectivePath ? 'is-ready' : 'is-warn') : 'is-cloud'}`}
        role="status"
        aria-live="polite"
      >
        <span className="runtime-status-icon" aria-hidden="true">
          {isWindows ? (
            workersLive ? <Wifi size={16} /> : <WifiOff size={16} />
          ) : (
            <Cloud size={16} />
          )}
        </span>
        <div className="runtime-status-copy">
          {isWindows ? (
            <>
              <strong>
                {workersLive && effectivePath
                  ? 'Windows готов'
                  : !effectivePath
                    ? 'Windows: нужен путь'
                    : 'Windows: воркер офлайн'}
              </strong>
              <span>
                {effectivePath
                  ? `${hostLabel || 'воркер'} · ${effectivePath}`
                  : 'Укажите папку на ПК и нажмите Сохранить, затем Windows.'}
                {!workersLive && effectivePath ? ' Запустите воркер, иначе задача не уйдёт.' : ''}
              </span>
            </>
          ) : (
            <>
              <strong>Cloud активен</strong>
              <span>
                {workersLive
                  ? `Windows-воркер онлайн (${hostLabel}) — можно переключить.`
                  : 'Задачи идут в облако Cursor.'}
              </span>
            </>
          )}
        </div>
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
          <button
            type="button"
            className={pathSaved && !pathDirty ? 'is-saved' : ''}
            disabled={!pathDirty || runtimeBusy}
            onClick={savePath}
          >
            {runtimeBusy ? (
              <Loader2 size={15} className="spin-icon" aria-hidden="true" />
            ) : pathSaved ? (
              <>
                <CheckCircle2 size={15} aria-hidden="true" /> Сохранено
              </>
            ) : (
              'Сохранить'
            )}
          </button>
        </div>
      </label>

      <AnimatePresence initial={false}>
        {flash && (
          <motion.div
            key={`${flash.title}-${flash.detail}`}
            className={`runtime-flash tone-${flash.tone}`}
            role="status"
            aria-live="polite"
            initial={reducedMotion ? false : { opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reducedMotion ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {flash.tone === 'ok' ? (
              <CheckCircle2 size={16} aria-hidden="true" />
            ) : (
              <WifiOff size={16} aria-hidden="true" />
            )}
            <div>
              <strong>{flash.title}</strong>
              <span>{flash.detail}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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
        {attachments.length > 0 && (
          <div className="prompt-attachments" aria-label="Вложения">
            {attachments.map((item) => (
              <div className="prompt-attachment" key={item.id}>
                <img src={item.previewUrl} alt="" />
                <button
                  type="button"
                  className="prompt-attachment-remove"
                  aria-label="Убрать картинку"
                  onClick={() => removeAttachment(item.id)}
                  disabled={promptBusy}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <textarea
          id="agent-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onPaste={(event) => {
            const files = Array.from(event.clipboardData?.files ?? []).filter((file) =>
              file.type.startsWith('image/'),
            )
            if (!files.length) return
            event.preventDefault()
            void addFiles(files)
          }}
          placeholder="Опишите задачу или вставьте скрин (Ctrl+V)…"
          rows={3}
          maxLength={8000}
          disabled={promptBusy}
        />
        <div className="prompt-form-actions">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            hidden
            onChange={(event) => {
              if (event.target.files) void addFiles(event.target.files)
              event.target.value = ''
            }}
          />
          <button
            type="button"
            className="prompt-attach-btn"
            disabled={promptBusy || attachments.length >= MAX_ATTACHMENTS}
            onClick={() => {
              feedback('tap')
              fileInputRef.current?.click()
            }}
          >
            <ImagePlus size={16} aria-hidden="true" />
            Скрин
          </button>
          <button
            type="submit"
            disabled={promptBusy || (!prompt.trim() && attachments.length === 0)}
          >
            {promptBusy ? <Loader2 size={16} className="spin-icon" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
            {MODE_LABELS[mode]}
          </button>
        </div>
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
