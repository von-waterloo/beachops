import { useEffect, useMemo, useRef, useState, type ClipboardEvent as ReactClipboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  ArrowLeft,
  ArrowRight,
  Captions,
  Check,
  Cloud,
  Expand,
  ImagePlus,
  Mic,
  MicOff,
  RotateCcw,
  Send,
  Square,
  X,
} from 'lucide-react'
import { requestTelegramFullscreen } from '../lib/telegram'
import { feedback } from '../lib/feedback'
import { setCursorModel, type CursorModelOption } from '../lib/passkeys'
import { useVoiceSession } from '../voice/useVoiceSession'
import { SPECTRUM_BAR_COUNT } from '../voice/constants'
import type { VoiceAgentMode, VoicePhase } from '../voice/state'
import type { Event, Job } from '../types/api'
import { runtimeLabel, statusLabel } from '../lib/uiCopy'
import {
  attachmentPayload,
  collectAttachments,
  isAcceptedImageFile,
  MAX_ATTACHMENTS,
  type PromptAttachment,
} from '../lib/promptAttachments'
import { JobChatPanel } from './JobChatPanel'

const CANCEL_SWIPE_PX = 72
const ATTACH_SWIPE_PX = 72
const MODEL_PREVIEW_COUNT = 4

const phaseLabels: Record<VoicePhase, string> = {
  idle: 'На посту',
  listening: 'Слушаю',
  transcribing: 'Разбираю',
  confirming: 'Подтверди',
  planning: 'В работе',
  speaking: 'Отвечаю',
  error: 'Сбой',
}

const modeLabels: Record<'ask' | 'do', string> = {
  ask: 'Чат',
  do: 'Действие',
}

const confirmLabels: Record<VoiceAgentMode, string> = {
  ask: 'Спросить',
  plan: 'В план',
  do: 'Сделать',
}

const phaseEnergy: Record<VoicePhase, number> = {
  idle: 0.08,
  listening: 0,
  transcribing: 0.28,
  confirming: 0.14,
  planning: 0.42,
  speaking: 0.36,
  error: 0.2,
}

interface SubmitPromptInput {
  prompt: string
  mode?: 'ask' | 'plan' | 'do'
  images?: Array<{ mimeType: string; data: string }>
}

interface SubmitPromptResult {
  job: { id: string }
  enqueued: boolean
  reason?: string
}

interface Props {
  activeJob?: Job | null
  latestEvent?: Event | null
  cursorModelKey?: string
  models?: CursorModelOption[]
  onModelChange?: (modelKey: string) => void
  onSubmitPrompt?: (input: SubmitPromptInput) => Promise<SubmitPromptResult>
}

export function VoiceConsole({
  activeJob = null,
  latestEvent = null,
  cursorModelKey,
  models = [],
  onModelChange,
  onSubmitPrompt,
}: Props) {
  const [composer, setComposer] = useState('')
  const [attachments, setAttachments] = useState<PromptAttachment[]>([])
  const [attachError, setAttachError] = useState<string | null>(null)
  const [promptBusy, setPromptBusy] = useState(false)
  const [pulse, setPulse] = useState(0.2)
  const [selectedModel, setSelectedModel] = useState(cursorModelKey ?? '')
  const [modelBusy, setModelBusy] = useState(false)
  const [modelsExpanded, setModelsExpanded] = useState(false)
  const [rippleKey, setRippleKey] = useState(0)
  const [agentMode, setAgentMode] = useState<VoiceAgentMode>('ask')
  const [dragX, setDragX] = useState(0)
  const [cancelArmed, setCancelArmed] = useState(false)
  const [attachArmed, setAttachArmed] = useState(false)
  const pointerStartX = useRef<number | null>(null)
  const dragXRef = useRef(0)
  const didSwipeRef = useRef(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const attachmentsRef = useRef(attachments)
  attachmentsRef.current = attachments
  const onSubmitPromptRef = useRef(onSubmitPrompt)
  onSubmitPromptRef.current = onSubmitPrompt

  const voice = useVoiceSession({
    shouldDeferAutoDispatch: () => attachmentsRef.current.length > 0,
    onDeferredAutoDispatch: async (text, mode) => {
      const submit = onSubmitPromptRef.current
      if (!submit) return
      setPromptBusy(true)
      setAttachError(null)
      try {
        const result = await submit({
          prompt: text,
          mode: mode === 'plan' ? 'plan' : mode,
          images: attachmentsRef.current.length
            ? attachmentPayload(attachmentsRef.current)
            : undefined,
        })
        if (!result.enqueued) {
          feedback('warning')
          setAttachError(result.reason || 'Запрос заблокирован')
          return
        }
        feedback('success')
        setAttachments([])
      } catch (err: unknown) {
        feedback('error')
        setAttachError(err instanceof Error ? err.message : 'Не удалось отправить')
      } finally {
        setPromptBusy(false)
      }
    },
  })
  const reducedMotion = useReducedMotion()
  const { state } = voice

  useEffect(() => {
    if (cursorModelKey) setSelectedModel(cursorModelKey)
  }, [cursorModelKey])

  useEffect(() => {
    if (!selectedModel || models.length <= MODEL_PREVIEW_COUNT) return
    const index = models.findIndex((model) => model.key === selectedModel)
    if (index >= MODEL_PREVIEW_COUNT) setModelsExpanded(true)
  }, [models, selectedModel])

  useEffect(() => {
    if (state.phase !== 'listening') {
      setDragX(0)
      setCancelArmed(false)
      setAttachArmed(false)
      pointerStartX.current = null
      didSwipeRef.current = false
    }
  }, [state.phase])

  const active = ['listening', 'transcribing', 'planning', 'speaking'].includes(state.phase)
  const canStart = ['idle', 'error', 'planning', 'speaking'].includes(state.phase)
  const showComposer = ['idle', 'error', 'planning', 'speaking'].includes(state.phase)
  const modeLocked = ['listening', 'transcribing'].includes(state.phase)

  useEffect(() => {
    if (reducedMotion || state.phase === 'listening') return undefined
    const target = phaseEnergy[state.phase]
    const timer = window.setInterval(() => {
      setPulse(target + Math.sin(Date.now() / 420) * 0.08)
    }, 80)
    return () => window.clearInterval(timer)
  }, [reducedMotion, state.phase])

  const displayEnergy = state.phase === 'listening'
    ? voice.energy
    : Math.max(phaseEnergy[state.phase], pulse)

  const jobCaption = useMemo(() => {
    if (!activeJob) return null
    const eventBit = latestEvent?.summary ? ` · ${latestEvent.summary}` : ''
    return `${runtimeLabel(activeJob.runtime)} · ${statusLabel(activeJob.status)}${eventBit}`
  }, [activeJob, latestEvent])

  const planningLabel = agentMode === 'ask'
    ? 'Чат'
    : agentMode === 'do'
      ? 'Действие'
      : 'План'

  const isListening = state.phase === 'listening'

  const statusTitle = cancelArmed
    ? 'Отмена'
    : attachArmed
      ? 'Скрин'
      : isListening
        ? 'Слушаю'
        : state.phase === 'planning'
          ? planningLabel
          : phaseLabels[state.phase]

  const statusSubtitle = cancelArmed
    ? 'Отпусти — запись не уйдёт'
    : attachArmed
      ? 'Отпусти — выбрать картинку'
      : isListening
        ? 'Отпусти — отправить'
        : state.queuedHint ?? state.caption

  const addFiles = async (files: FileList | File[]) => {
    try {
      let nextState: PromptAttachment[] = attachmentsRef.current
      let error: string | null = null
      const collected = await collectAttachments(files, attachmentsRef.current)
      nextState = collected.next
      error = collected.error
      attachmentsRef.current = nextState
      setAttachments(nextState)
      if (error) {
        setAttachError(error)
        feedback(nextState.length > attachments.length ? 'select' : 'warning')
        return
      }
      setAttachError(null)
      feedback('select')
    } catch (err: unknown) {
      feedback('error')
      setAttachError(err instanceof Error ? err.message : 'Не удалось добавить картинку')
    }
  }

  const openFilePicker = () => {
    if (attachmentsRef.current.length >= MAX_ATTACHMENTS) {
      setAttachError(`Максимум ${MAX_ATTACHMENTS} скринов за раз`)
      feedback('warning')
      return
    }
    fileInputRef.current?.click()
  }

  const handleMode = (mode: 'ask' | 'do') => {
    if (modeLocked || mode === agentMode) return
    feedback('select')
    setAgentMode(mode)
    voice.setMode(mode)
  }

  const handleOrb = () => {
    if (didSwipeRef.current) {
      didSwipeRef.current = false
      return
    }
    feedback('tap')
    setRippleKey((key) => key + 1)
    if (state.phase === 'listening') voice.finishListening()
    else if (canStart) void voice.startListening()
  }

  const onOrbPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (state.phase !== 'listening') return
    pointerStartX.current = event.clientX
    dragXRef.current = 0
    didSwipeRef.current = false
    setCancelArmed(false)
    setAttachArmed(false)
    setDragX(0)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onOrbPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (state.phase !== 'listening' || pointerStartX.current === null) return
    const delta = event.clientX - pointerStartX.current
    dragXRef.current = delta
    setDragX(delta)
    const cancel = delta <= -CANCEL_SWIPE_PX
    const attach = delta >= ATTACH_SWIPE_PX
    if (cancel !== cancelArmed) setCancelArmed(cancel)
    if (attach !== attachArmed) setAttachArmed(attach)
  }

  const onOrbPointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (state.phase !== 'listening' || pointerStartX.current === null) return
    pointerStartX.current = null
    const delta = dragXRef.current
    dragXRef.current = 0
    setDragX(0)
    try {
      event.currentTarget.releasePointerCapture(event.pointerId)
    } catch {
      // ignore if capture was already released
    }
    if (delta <= -CANCEL_SWIPE_PX) {
      didSwipeRef.current = true
      setCancelArmed(false)
      setAttachArmed(false)
      voice.cancelListening()
      return
    }
    if (delta >= ATTACH_SWIPE_PX) {
      didSwipeRef.current = true
      setCancelArmed(false)
      setAttachArmed(false)
      openFilePicker()
      return
    }
    setCancelArmed(false)
    setAttachArmed(false)
  }

  const dispatchPrompt = async (prompt: string) => {
    if (!onSubmitPrompt) return false
    setPromptBusy(true)
    setAttachError(null)
    try {
      const result = await onSubmitPrompt({
        prompt,
        mode: agentMode === 'plan' ? 'plan' : agentMode,
        images: attachments.length ? attachmentPayload(attachments) : undefined,
      })
      if (!result.enqueued) {
        feedback('warning')
        setAttachError(result.reason || 'Запрос заблокирован')
        return false
      }
      feedback('success')
      setAttachments([])
      return true
    } catch (err: unknown) {
      feedback('error')
      setAttachError(err instanceof Error ? err.message : 'Не удалось отправить')
      return false
    } finally {
      setPromptBusy(false)
    }
  }

  const handleComposer = () => {
    const trimmed = composer.trim()
    if ((!trimmed && attachments.length === 0) || promptBusy) return
    if (attachments.length > 0) {
      void dispatchPrompt(trimmed).then((ok) => {
        if (ok) setComposer('')
      })
      return
    }
    if (voice.submitComposer(composer)) setComposer('')
  }

  const handleConfirm = () => {
    const trimmed = state.transcript.trim()
    if ((!trimmed && attachments.length === 0) || promptBusy) return
    if (attachments.length > 0) {
      void dispatchPrompt(trimmed).then((ok) => {
        if (ok) voice.cancel()
      })
      return
    }
    voice.confirmPlan()
  }

  const onPasteImages = (event: ReactClipboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files || []).filter(isAcceptedImageFile)
    if (!files.length) return
    event.preventDefault()
    void addFiles(files)
  }

  const handleModelSelect = async (modelKey: string) => {
    if (modelKey === selectedModel || modelBusy) return
    setModelBusy(true)
    try {
      await setCursorModel(modelKey)
      setSelectedModel(modelKey)
      onModelChange?.(modelKey)
      feedback('success')
    } catch {
      feedback('error')
    } finally {
      setModelBusy(false)
    }
  }

  return (
    <section className="voice-console" aria-label="Диалог">

      {models.length > 0 && (
        <div className="model-picker" role="group" aria-label="Модель Cursor">
          {(modelsExpanded ? models : models.slice(0, MODEL_PREVIEW_COUNT)).map((model) => {
            const selected = model.key === selectedModel
            return (
              <button
                key={model.key}
                type="button"
                className={`model-chip${selected ? ' is-selected' : ''}`}
                aria-pressed={selected}
                disabled={modelBusy}
                onClick={() => {
                  feedback('tap')
                  void handleModelSelect(model.key)
                }}
              >
                {selected ? <Check size={12} aria-hidden="true" /> : null}
                <span>{model.label}</span>
              </button>
            )
          })}
          {models.length > MODEL_PREVIEW_COUNT && (
            <button
              type="button"
              className="model-chip model-chip-more"
              aria-expanded={modelsExpanded}
              onClick={() => {
                feedback('select')
                setModelsExpanded((open) => !open)
              }}
            >
              <span>{modelsExpanded ? 'Свернуть' : `Ещё ${models.length - MODEL_PREVIEW_COUNT}`}</span>
            </button>
          )}
        </div>
      )}

      <div className={`voice-stage phase-${state.phase} ${active ? 'is-active' : ''} ${cancelArmed ? 'is-cancel' : ''} ${attachArmed ? 'is-attach' : ''}`}>
        {!reducedMotion && (
          <div className="particles" aria-hidden="true">
            {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
          multiple
          hidden
          onChange={(event) => {
            if (event.target.files?.length) void addFiles(event.target.files)
            event.target.value = ''
          }}
        />

        <div className="voice-stage-top">
          {!isListening && activeJob ? (
            <div className="job-chip" role="status">
              <Cloud size={12} />
              <span>{activeJob.title.slice(0, 36)}</span>
            </div>
          ) : (
            <span className="voice-stage-top-spacer" aria-hidden="true" />
          )}
          <div className="voice-stage-top-actions">
            {!isListening && (
              <div className="connection-chip">
                <span className={state.connected ? 'online-dot' : 'offline-dot'} />
                {state.connected ? 'На связи' : 'Переподключаюсь'}
              </div>
            )}
            <button
              className="icon-button icon-button-compact"
              type="button"
              aria-label="На весь экран"
              onClick={() => {
                feedback('tap')
                requestTelegramFullscreen()
              }}
            >
              <Expand size={16} />
            </button>
          </div>
        </div>

        <div className="voice-stage-center">
          <div className="voice-mode-toggle" role="toolbar" aria-label="Режим">
            {(['ask', 'do'] as const).map((item) => (
              <button
                key={item}
                type="button"
                className={agentMode === item ? 'selected' : ''}
                aria-pressed={agentMode === item}
                disabled={modeLocked}
                onClick={() => handleMode(item)}
              >
                {modeLabels[item]}
              </button>
            ))}
          </div>

          <div className="orb-row">
            {isListening && (
              <div
                className={`orb-swipe-hint is-left${cancelArmed ? ' is-armed' : ''}`}
                aria-hidden="true"
              >
                <ArrowLeft size={18} strokeWidth={2.2} />
                <X size={15} />
                <span>Отмена</span>
              </div>
            )}

          <motion.button
            type="button"
            className={`orb-button${cancelArmed ? ' is-cancel' : ''}${attachArmed ? ' is-attach' : ''}`}
            aria-label={
              state.phase === 'listening'
                ? (cancelArmed
                  ? 'Отменить запись'
                  : attachArmed
                    ? 'Прикрепить картинку'
                    : 'Отправить · влево отмена · вправо скрин')
                : 'Говорить'
            }
            aria-pressed={state.phase === 'listening'}
            onClick={handleOrb}
            onPointerDown={onOrbPointerDown}
            onPointerMove={onOrbPointerMove}
            onPointerUp={onOrbPointerUp}
            onPointerCancel={onOrbPointerUp}
            whileTap={reducedMotion || state.phase === 'listening' ? undefined : { scale: 0.9 }}
            whileHover={reducedMotion ? undefined : { scale: 1.03 }}
            animate={{
              x: state.phase === 'listening' ? dragX * 0.45 : 0,
              scale: 1 + displayEnergy * (state.phase === 'listening' ? 0.06 : 0.02),
            }}
            transition={{ type: 'spring', stiffness: 460, damping: 24 }}
          >
            {!reducedMotion && rippleKey > 0 && (
              <span key={`ripple-${rippleKey}`} className="orb-ripple is-firing" aria-hidden="true" />
            )}
            {!reducedMotion && rippleKey > 0 && (
              <span key={`flash-${rippleKey}`} className="orb-press-flash is-firing" aria-hidden="true" />
            )}
            {!reducedMotion && isListening && !cancelArmed && !attachArmed && (
              <>
                <span className="orb-ring orb-ring-1" aria-hidden="true" />
                <span className="orb-ring orb-ring-2" aria-hidden="true" />
              </>
            )}
            <span
              className="orb-halo"
              style={{
                opacity: 0.35 + displayEnergy * 0.45,
                transform: `scale(${1 + displayEnergy * 0.18})`,
              }}
            />
            <span className="orb-glass" aria-hidden="true" />
            <span className="orb-core">
              {state.phase === 'listening'
                ? (cancelArmed
                  ? <X size={28} />
                  : attachArmed
                    ? <ImagePlus size={28} />
                    : <Square size={26} fill="currentColor" />)
                : <Mic size={30} />}
            </span>
          </motion.button>

            {isListening && (
              <div
                className={`orb-swipe-hint is-right${attachArmed ? ' is-armed' : ''}`}
                aria-hidden="true"
              >
                <ArrowRight size={18} strokeWidth={2.2} />
                <ImagePlus size={15} />
                <span>Скрин</span>
              </div>
            )}
          </div>

          <div className="spectrum" aria-hidden="true">
            {(state.phase === 'listening' ? voice.spectrum : Array.from({ length: SPECTRUM_BAR_COUNT }, (_, i) =>
              Math.max(0.08, displayEnergy * (0.45 + 0.55 * Math.abs(Math.sin((i + 1) * 0.55 + displayEnergy * 4)))),
            )).map((value, index) => (
              <motion.i
                key={index}
                animate={{ scaleY: reducedMotion ? 0.3 : Math.max(0.12, value) }}
                transition={{
                  type: 'spring',
                  stiffness: 440,
                  damping: 32,
                  delay: state.phase === 'listening' ? index * 0.012 : 0,
                }}
              />
            ))}
          </div>
        </div>

        <div className="voice-stage-footer">
          <AnimatePresence mode="wait">
            <motion.div
              key={`${state.phase}-${jobCaption ?? ''}-${cancelArmed ? 'c' : attachArmed ? 'a' : 'n'}`}
              className="voice-status"
              initial={reducedMotion ? false : { opacity: 0, y: 8, filter: 'blur(5px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={reducedMotion ? undefined : { opacity: 0, y: -6 }}
            >
              <strong>{statusTitle}</strong>
              {statusSubtitle && (
                <p aria-live="polite">{statusSubtitle}</p>
              )}
              {jobCaption && !cancelArmed && !attachArmed && !isListening && (
                <small className="job-status-caption">{jobCaption}</small>
              )}
            </motion.div>
          </AnimatePresence>

          {isListening && cancelArmed && (
            <motion.div
              className="privacy-chip is-cancel"
              role="status"
              initial={reducedMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <span className="privacy-pulse" />
              Отмена отправки
            </motion.div>
          )}
          {isListening && attachArmed && (
            <motion.div
              className="privacy-chip is-attach"
              role="status"
              initial={reducedMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <span className="privacy-pulse" />
              Прикрепить скрин
            </motion.div>
          )}
          {isListening && attachments.length > 0 && !cancelArmed && (
            <div className="attachment-row voice-attach-row" aria-label="Вложения">
              {attachments.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="attachment-thumb"
                  title="Убрать"
                  onClick={() => {
                    feedback('tap')
                    setAttachments((prev) => {
                      const next = prev.filter((entry) => entry.id !== item.id)
                      attachmentsRef.current = next
                      return next
                    })
                  }}
                >
                  <img src={item.previewUrl} alt="" />
                  <X size={12} />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <JobChatPanel
        jobId={activeJob?.id ?? null}
        enabled={Boolean(activeJob?.id)}
        liveCaption={state.caption}
        pollMs={1_500}
      />

      {showComposer && (
        <div className="composer-card voice-manual-compose">
          <label htmlFor="voice-composer">
            {state.phase === 'planning' || state.phase === 'speaking'
              ? 'Ещё в очередь'
              : 'Приказ'}
          </label>
          {attachments.length > 0 && (
            <div className="attachment-row" aria-label="Вложения">
              {attachments.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="attachment-thumb"
                  title="Убрать"
                  onClick={() => {
                    feedback('tap')
                    setAttachments((prev) => prev.filter((entry) => entry.id !== item.id))
                  }}
                >
                  <img src={item.previewUrl} alt="" />
                  <X size={12} />
                </button>
              ))}
            </div>
          )}
          <div className="composer-row">
            <button
              type="button"
              className="ghost-button composer-attach"
              title="Прикрепить картинку"
              aria-label="Прикрепить картинку"
              disabled={promptBusy || attachments.length >= MAX_ATTACHMENTS}
              onClick={() => {
                feedback('tap')
                openFilePicker()
              }}
            >
              <ImagePlus size={18} />
            </button>
            <input
              id="voice-composer"
              type="text"
              value={composer}
              maxLength={4000}
              placeholder={agentMode === 'do' ? 'Что сделать в репо.' : 'Короткий вопрос.'}
              onChange={(event) => setComposer(event.target.value)}
              onPaste={onPasteImages}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  handleComposer()
                }
              }}
            />
            <button
              className="primary-button composer-send"
              type="button"
              disabled={promptBusy || (!composer.trim() && attachments.length === 0)}
              onClick={handleComposer}
              aria-label="Отправить"
            >
              <Send size={17} />
            </button>
          </div>
          {attachError && <div className="inline-error" role="alert">{attachError}</div>}
        </div>
      )}

      <AnimatePresence>
        {state.phase === 'confirming' && (
          <motion.div
            className="transcript-card"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <label htmlFor="voice-transcript">
              <Captions size={16} />
              Распознано
            </label>
            <textarea
              id="voice-transcript"
              value={state.transcript}
              onChange={(event) => voice.editTranscript(event.target.value)}
              onPaste={onPasteImages}
              rows={4}
              maxLength={4000}
              autoFocus
            />
            {attachments.length > 0 && (
              <div className="attachment-row" aria-label="Вложения">
                {attachments.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="attachment-thumb"
                    title="Убрать"
                    onClick={() => {
                      feedback('tap')
                      setAttachments((prev) => prev.filter((entry) => entry.id !== item.id))
                    }}
                  >
                    <img src={item.previewUrl} alt="" />
                    <X size={12} />
                  </button>
                ))}
              </div>
            )}
            <div className="composer-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={attachments.length >= MAX_ATTACHMENTS}
                onClick={() => {
                  feedback('tap')
                  openFilePicker()
                }}
              >
                <ImagePlus size={16} /> Скрин
              </button>
            </div>
            <p className="security-note">
              {agentMode === 'do'
                ? 'Режим действия: после отправки агент пойдёт в репо.'
                : 'Режим чата: ответит коротко, код не меняет.'}
            </p>
            <div className="action-row">
              <button className="secondary-button" type="button" onClick={voice.cancel}>
                <X size={17} /> Отмена
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={handleConfirm}
                disabled={promptBusy || (!state.transcript.trim() && attachments.length === 0)}
              >
                <Send size={17} /> {confirmLabels[agentMode]}
              </button>
            </div>
            {attachError && <div className="inline-error" role="alert">{attachError}</div>}
          </motion.div>
        )}
      </AnimatePresence>

      {state.phase === 'error' && (
        <div className="error-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              feedback('select')
              voice.reset()
            }}
          >
            <RotateCcw size={17} /> Ещё раз
          </button>
        </div>
      )}

      {state.phase === 'planning' && agentMode === 'do' && (
        <div className="plan-safety" role="status">
          <Check size={17} /> Действие: пишу и пушу в выбранную базу.
        </div>
      )}

      {!isListening && (
        <>
          <div className="voice-footnote">
            {state.phase === 'speaking'
              ? <><Mic size={14} /> Кнопка — прервать и сказать ещё</>
              : <><MicOff size={14} /> Можно кидать несколько сообщений подряд в очередь</>}
          </div>
          <p className="telegram-workflow-hint">
            Ответ стримится и в Mini App, и в Telegram-боте — один поток.
          </p>
        </>
      )}
    </section>
  )
}
