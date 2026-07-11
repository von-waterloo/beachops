import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  Bot,
  ImagePlus,
  Loader2,
  Plus,
  Send,
  Trash2,
  X,
} from 'lucide-react'
import type { AgentSlot } from '../types/api'
import { feedback } from '../lib/feedback'

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
  label?: string
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
  role: string
  queuedCount?: number
  onUpdateAgent: (slotId: string, input: UpdateAgentInput) => Promise<void>
  onCreateAgent?: () => Promise<void>
  onDeleteAgent?: (slotId: string) => Promise<void>
  onSubmitPrompt: (input: SubmitPromptInput) => Promise<SubmitPromptResult>
  onJobDispatched?: (jobId: string) => void
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

export function AgentControlPanel({
  slots,
  role,
  queuedCount = 0,
  onUpdateAgent,
  onCreateAgent,
  onDeleteAgent,
  onSubmitPrompt,
  onJobDispatched,
}: AgentControlPanelProps) {
  const activeSlot = slots.find((slot) => slot.active) ?? slots[0] ?? null
  const [prompt, setPrompt] = useState('')
  const [attachments, setAttachments] = useState<PromptAttachment[]>([])
  const [mode, setMode] = useState<PromptMode>('ask')
  const [promptBusy, setPromptBusy] = useState(false)
  const [slotBusy, setSlotBusy] = useState(false)
  const [promptError, setPromptError] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    setRenameValue(activeSlot?.label ?? '')
  }, [activeSlot?.id, activeSlot?.label])

  useEffect(() => {
    if (!canUseMode(role, mode)) setMode('ask')
  }, [role, mode])

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

  if (!activeSlot) {
    return (
      <motion.section
        className="agent-control"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <header className="agent-control-header">
          <p className="eyebrow">Агенты</p>
          <h2>Нет слотов</h2>
          <p className="muted-hint">Создай первого cloud-агента.</p>
        </header>
        {onCreateAgent && (
          <button
            type="button"
            className="primary-button"
            disabled={slotBusy}
            onClick={() => {
              setSlotBusy(true)
              void onCreateAgent().finally(() => setSlotBusy(false))
            }}
          >
            <Plus size={16} /> Новый агент
          </button>
        )}
      </motion.section>
    )
  }

  const send = () => {
    if ((!prompt.trim() && attachments.length === 0) || promptBusy) return
    if (!canUseMode(role, mode)) {
      setPromptError('Этот режим недоступен для вашей роли')
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
        onJobDispatched?.(result.job.id)
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
        <p className="eyebrow">Работа</p>
        <h2>{activeSlot.label}</h2>
        <p className="muted-hint">
          Cloud Cursor · ask / plan / do
          {queuedCount > 0 ? ` · в очереди ${queuedCount}` : ''}
        </p>
      </header>

      <div className="agent-switcher" role="listbox" aria-label="Агенты">
        {slots.map((slot) => (
          <button
            key={slot.id}
            type="button"
            role="option"
            aria-selected={slot.id === activeSlot.id}
            className={slot.id === activeSlot.id ? 'selected' : ''}
            disabled={slotBusy}
            onClick={() => {
              if (slot.id === activeSlot.id) return
              setSlotBusy(true)
              feedback('select')
              void onUpdateAgent(slot.id, { makeActive: true })
                .finally(() => setSlotBusy(false))
            }}
          >
            <Bot size={14} aria-hidden="true" />
            <span>{slot.label}</span>
          </button>
        ))}
        {onCreateAgent && (
          <button
            type="button"
            className="ghost"
            disabled={slotBusy}
            onClick={() => {
              setSlotBusy(true)
              feedback('tap')
              void onCreateAgent().finally(() => setSlotBusy(false))
            }}
            aria-label="Новый агент"
          >
            <Plus size={14} />
          </button>
        )}
      </div>

      <div className="agent-rename-row">
        <input
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          maxLength={64}
          aria-label="Имя агента"
          disabled={slotBusy}
        />
        <button
          type="button"
          disabled={
            slotBusy
            || !renameValue.trim()
            || renameValue.trim() === activeSlot.label
          }
          onClick={() => {
            setSlotBusy(true)
            void onUpdateAgent(activeSlot.id, { label: renameValue.trim() })
              .finally(() => setSlotBusy(false))
          }}
        >
          Переименовать
        </button>
        {onDeleteAgent && slots.length > 1 && (
          <button
            type="button"
            className="danger-ghost"
            disabled={slotBusy}
            aria-label="Удалить агента"
            onClick={() => {
              if (!window.confirm(`Удалить агента «${activeSlot.label}»?`)) return
              setSlotBusy(true)
              void onDeleteAgent(activeSlot.id).finally(() => setSlotBusy(false))
            }}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>

      <div className="composer-mode-row" role="toolbar" aria-label="Режим">
        {(['ask', 'plan', 'do'] as const).map((item) => {
          const allowed = canUseMode(role, item)
          return (
            <button
              key={item}
              type="button"
              className={mode === item ? 'selected' : ''}
              aria-pressed={mode === item}
              disabled={!allowed}
              onClick={() => {
                feedback('select')
                setMode(item)
              }}
            >
              {MODE_LABELS[item]}
            </button>
          )
        })}
      </div>

      <div className="composer-card">
        <label htmlFor="agent-prompt">Задача</label>
        <textarea
          id="agent-prompt"
          value={prompt}
          rows={4}
          maxLength={8000}
          placeholder={
            mode === 'ask'
              ? 'Вопрос по коду…'
              : mode === 'plan'
                ? 'Что спланировать…'
                : 'Что сделать в репо…'
          }
          onChange={(event) => setPrompt(event.target.value)}
          disabled={promptBusy}
        />

        <AnimatePresence initial={false}>
          {attachments.length > 0 && (
            <motion.div
              className="attachment-row"
              initial={reducedMotion ? false : { opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={reducedMotion ? undefined : { opacity: 0, height: 0 }}
            >
              {attachments.map((item) => (
                <div key={item.id} className="attachment-thumb">
                  <img src={item.previewUrl} alt="" />
                  <button
                    type="button"
                    aria-label="Убрать"
                    onClick={() => {
                      setAttachments((prev) => prev.filter((x) => x.id !== item.id))
                      feedback('select')
                    }}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="composer-actions">
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
            className="ghost-button"
            disabled={promptBusy || attachments.length >= MAX_ATTACHMENTS}
            onClick={() => fileInputRef.current?.click()}
          >
            <ImagePlus size={16} /> Скрин
          </button>
          <button
            type="button"
            className="primary-button composer-send"
            disabled={promptBusy || (!prompt.trim() && attachments.length === 0)}
            onClick={send}
          >
            {promptBusy ? (
              <Loader2 size={16} className="spin-icon" aria-hidden="true" />
            ) : (
              <Send size={16} aria-hidden="true" />
            )}
            Отправить
          </button>
        </div>
        {promptError && <div className="inline-error" role="alert">{promptError}</div>}
      </div>
    </motion.section>
  )
}
