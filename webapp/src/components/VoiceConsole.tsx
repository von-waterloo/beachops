import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  Captions,
  Check,
  Cloud,
  Expand,
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

const CANCEL_SWIPE_PX = 72
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

interface Props {
  activeJob?: Job | null
  latestEvent?: Event | null
  cursorModelKey?: string
  models?: CursorModelOption[]
  onModelChange?: (modelKey: string) => void
}

export function VoiceConsole({
  activeJob = null,
  latestEvent = null,
  cursorModelKey,
  models = [],
  onModelChange,
}: Props) {
  const voice = useVoiceSession()
  const reducedMotion = useReducedMotion()
  const { state } = voice
  const [composer, setComposer] = useState('')
  const [pulse, setPulse] = useState(0.2)
  const [selectedModel, setSelectedModel] = useState(cursorModelKey ?? '')
  const [modelBusy, setModelBusy] = useState(false)
  const [modelsExpanded, setModelsExpanded] = useState(false)
  const [rippleKey, setRippleKey] = useState(0)
  const [agentMode, setAgentMode] = useState<VoiceAgentMode>('ask')
  const [dragX, setDragX] = useState(0)
  const [cancelArmed, setCancelArmed] = useState(false)
  const pointerStartX = useRef<number | null>(null)
  const dragXRef = useRef(0)
  const didSwipeRef = useRef(false)

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
    : isListening
      ? 'Слушаю'
      : state.phase === 'planning'
        ? planningLabel
        : phaseLabels[state.phase]

  const statusSubtitle = cancelArmed
    ? 'Отпусти — запись не уйдёт'
    : isListening
      ? null
      : state.queuedHint ?? state.caption

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
    setDragX(0)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onOrbPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (state.phase !== 'listening' || pointerStartX.current === null) return
    const delta = Math.min(0, event.clientX - pointerStartX.current)
    dragXRef.current = delta
    setDragX(delta)
    const armed = delta <= -CANCEL_SWIPE_PX
    if (armed !== cancelArmed) setCancelArmed(armed)
  }

  const onOrbPointerUp = () => {
    if (state.phase !== 'listening' || pointerStartX.current === null) return
    pointerStartX.current = null
    const delta = dragXRef.current
    dragXRef.current = 0
    setDragX(0)
    if (delta <= -CANCEL_SWIPE_PX) {
      didSwipeRef.current = true
      setCancelArmed(false)
      voice.cancelListening()
      return
    }
    setCancelArmed(false)
  }

  const handleComposer = () => {
    if (voice.submitComposer(composer)) setComposer('')
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
    <section className="voice-console" aria-labelledby="voice-heading">
      <header className="voice-heading">
        <div>
          <p className="eyebrow">Диалог</p>
          <h1 id="voice-heading">BeachOps</h1>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="На весь экран"
          onClick={() => {
            feedback('tap')
            requestTelegramFullscreen()
          }}
        >
          <Expand size={18} />
        </button>
      </header>

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

      <div className={`voice-stage phase-${state.phase} ${active ? 'is-active' : ''} ${cancelArmed ? 'is-cancel' : ''}`}>
        {!reducedMotion && (
          <div className="particles" aria-hidden="true">
            {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
          </div>
        )}
        {!isListening && (
          <>
            <div className="connection-chip">
              <span className={state.connected ? 'online-dot' : 'offline-dot'} />
              {state.connected ? 'На связи' : 'Переподключаюсь'}
            </div>

            {activeJob && (
              <div className="job-chip" role="status">
                <Cloud size={12} />
                <span>{activeJob.title.slice(0, 42)}</span>
              </div>
            )}
          </>
        )}

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

          <motion.button
            type="button"
            className={`orb-button${cancelArmed ? ' is-cancel' : ''}`}
            aria-label={
              state.phase === 'listening'
                ? (cancelArmed ? 'Отменить запись' : 'Отправить · влево отмена')
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
            {!reducedMotion && isListening && !cancelArmed && (
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
                ? (cancelArmed ? <X size={28} /> : <Square size={26} fill="currentColor" />)
                : <Mic size={30} />}
            </span>
          </motion.button>

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
              key={`${state.phase}-${jobCaption ?? ''}-${cancelArmed ? 'c' : 'n'}`}
              className="voice-status"
              initial={reducedMotion ? false : { opacity: 0, y: 8, filter: 'blur(5px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={reducedMotion ? undefined : { opacity: 0, y: -6 }}
            >
              <strong>{statusTitle}</strong>
              {statusSubtitle && (
                <p aria-live="polite">{statusSubtitle}</p>
              )}
              {jobCaption && !cancelArmed && !isListening && (
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
        </div>
      </div>

      {showComposer && (
        <div className="composer-card">
          <label htmlFor="voice-composer">
            {state.phase === 'planning' || state.phase === 'speaking'
              ? 'Ещё в очередь'
              : 'Приказ'}
          </label>
          <div className="composer-row">
            <input
              id="voice-composer"
              type="text"
              value={composer}
              maxLength={4000}
              placeholder={agentMode === 'do' ? 'Что сделать в репо.' : 'Короткий вопрос.'}
              onChange={(event) => setComposer(event.target.value)}
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
              disabled={!composer.trim()}
              onClick={handleComposer}
              aria-label="Отправить"
            >
              <Send size={17} />
            </button>
          </div>
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
              rows={4}
              maxLength={4000}
              autoFocus
            />
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
                onClick={voice.confirmPlan}
                disabled={!state.transcript.trim()}
              >
                <Send size={17} /> {confirmLabels[agentMode]}
              </button>
            </div>
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
