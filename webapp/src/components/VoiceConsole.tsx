import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  Captions,
  Check,
  Cloud,
  Expand,
  Mic,
  MicOff,
  Monitor,
  RotateCcw,
  Send,
  Square,
  X,
} from 'lucide-react'
import { requestTelegramFullscreen } from '../lib/telegram'
import { feedback } from '../lib/feedback'
import { setCursorModel, type CursorModelOption } from '../lib/auth'
import { useVoiceSession } from '../voice/useVoiceSession'
import type { VoiceAgentMode, VoicePhase } from '../voice/state'
import type { Event, Job } from '../types/api'
import { runtimeLabel, statusLabel } from '../lib/uiCopy'

const MODE_LABELS: Record<VoiceAgentMode, string> = {
  ask: 'Спросить',
  plan: 'План',
  do: 'Действие',
}

const MODE_SUBMIT_LABELS: Record<VoiceAgentMode, string> = {
  ask: 'Спросить',
  plan: 'В план',
  do: 'Сделать',
}

const phaseLabels: Record<VoicePhase, string> = {
  idle: 'Готов',
  listening: 'Слушаю',
  transcribing: 'Разбираю',
  confirming: 'Подтверди',
  planning: 'В эфире',
  speaking: 'Отвечаю',
  error: 'Сбой',
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

function jobChipTitle(title: string): string {
  const raw = title.trim()
  if (raw.startsWith('Ситуация BeachOps')) {
    const marker = 'Запрос пользователя:\n'
    const idx = raw.indexOf(marker)
    if (idx >= 0) {
      const userBit = raw.slice(idx + marker.length).trim()
      if (userBit) return userBit.slice(0, 42)
    }
    return 'Задача'
  }
  return raw.slice(0, 42)
}

interface Props {
  activeJob?: Job | null
  latestEvent?: Event | null
  cursorModelKey?: string
  models?: CursorModelOption[]
  onModelChange?: (modelKey: string) => void
  onJobStarted?: (jobId: string) => void
}

export function VoiceConsole({
  activeJob = null,
  latestEvent = null,
  cursorModelKey,
  models = [],
  onModelChange,
  onJobStarted,
}: Props) {
  const voice = useVoiceSession({ onJobStarted })
  const reducedMotion = useReducedMotion()
  const { state } = voice
  const [composer, setComposer] = useState('')
  const [agentMode, setAgentMode] = useState<VoiceAgentMode>('ask')
  const [pulse, setPulse] = useState(0.2)
  const [selectedModel, setSelectedModel] = useState(cursorModelKey ?? '')
  const [modelBusy, setModelBusy] = useState(false)
  const [modelError, setModelError] = useState<string | null>(null)

  useEffect(() => {
    if (cursorModelKey) setSelectedModel(cursorModelKey)
  }, [cursorModelKey])

  const active = ['listening', 'transcribing', 'planning', 'speaking'].includes(state.phase)
  const canStart = ['idle', 'error'].includes(state.phase)
  const showComposer = ['idle', 'error'].includes(state.phase)
  const showModeSwitch = ['idle', 'error', 'confirming'].includes(state.phase)

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

  const handleOrb = () => {
    if (state.phase === 'listening') voice.finishListening()
    else if (state.phase === 'speaking') void voice.startListening()
    else if (canStart) void voice.startListening()
  }

  const handleComposer = () => {
    if (voice.submitComposer(composer, agentMode)) setComposer('')
  }

  const selectMode = (mode: VoiceAgentMode) => {
    feedback('select')
    setAgentMode(mode)
    voice.setSubmitMode(mode)
  }

  const handleModelSelect = async (modelKey: string) => {
    if (modelKey === selectedModel || modelBusy) return
    setModelBusy(true)
    setModelError(null)
    try {
      await setCursorModel(modelKey)
      setSelectedModel(modelKey)
      onModelChange?.(modelKey)
      feedback('success')
    } catch (err: unknown) {
      feedback('error')
      setModelError(err instanceof Error ? err.message : 'Не удалось сменить модель')
    } finally {
      setModelBusy(false)
    }
  }

  const modeToolbar = showModeSwitch ? (
    <div className="composer-mode-row voice-mode-row" role="toolbar" aria-label="Режим запроса">
      {(['ask', 'plan', 'do'] as const).map((mode) => (
        <button
          key={mode}
          type="button"
          className={agentMode === mode ? 'selected' : ''}
          aria-pressed={agentMode === mode}
          onClick={() => selectMode(mode)}
        >
          {MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  ) : null

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
          {models.map((model) => {
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
        </div>
      )}
      {modelError && <div className="inline-error" role="alert">{modelError}</div>}

      {modeToolbar}

      <div className={`voice-stage phase-${state.phase} ${active ? 'is-active' : ''}`}>
        {!reducedMotion && (
          <div className="particles" aria-hidden="true">
            {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
          </div>
        )}
        <div className="voice-stage-top">
          <div className="voice-stage-top-left">
            {activeJob && (
              <div className="job-chip" role="status">
                {activeJob.runtime === 'windows' ? <Monitor size={12} /> : <Cloud size={12} />}
                <span>{jobChipTitle(activeJob.title)}</span>
              </div>
            )}
          </div>
          <div className="voice-stage-top-right">
            {(state.phase === 'planning' || state.speakingKind === 'milestone') && (
              <div className="air-chip" role="status">
                <span className="air-pulse" aria-hidden="true" />
                Эфир
              </div>
            )}
            <div className="connection-chip">
              <span className={state.connected ? 'online-dot' : 'offline-dot'} />
              {state.connected
                ? 'На связи'
                : state.phase === 'error'
                  ? 'Нет канала'
                  : 'По запросу'}
            </div>
          </div>
        </div>

        <button
          type="button"
          className={`orb-button phase-${state.phase}${active ? ' is-live' : ''}`}
          aria-label={state.phase === 'listening' ? 'Стоп' : 'Говорить'}
          aria-pressed={state.phase === 'listening'}
          onClick={handleOrb}
          style={{ '--orb-energy': String(displayEnergy) } as CSSProperties}
        >
          {!reducedMotion && (
            <>
              <span className="orb-radar" aria-hidden="true">
                <i /><i /><i />
              </span>
              <span className="orb-scan" aria-hidden="true" />
              <span className="orb-ticks" aria-hidden="true">
                {Array.from({ length: 24 }, (_, index) => <i key={index} />)}
              </span>
            </>
          )}
          <span className="orb-halo" aria-hidden="true" />
          <span className="orb-core">
            {state.phase === 'listening' ? <Square size={28} fill="currentColor" /> : <Mic size={32} />}
          </span>
        </button>

        <div className="spectrum" aria-hidden="true">
          {(state.phase === 'listening' ? voice.spectrum : Array.from({ length: 24 }, (_, i) =>
            Math.max(0.08, displayEnergy * (0.45 + 0.55 * Math.abs(Math.sin((i + 1) * 0.55 + displayEnergy * 4)))),
          )).map((value, index) => (
            <motion.i
              key={index}
              animate={{ scaleY: reducedMotion ? 0.3 : Math.max(0.12, value) }}
              transition={{ type: 'spring', stiffness: 440, damping: 32 }}
            />
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={`${state.phase}-${jobCaption ?? ''}`}
            className="voice-status"
            initial={reducedMotion ? false : { opacity: 0, y: 8, filter: 'blur(5px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={reducedMotion ? undefined : { opacity: 0, y: -6 }}
          >
            <strong>{phaseLabels[state.phase]}</strong>
            <p aria-live="polite">{state.caption}</p>
            {jobCaption && <small className="job-status-caption">{jobCaption}</small>}
          </motion.div>
        </AnimatePresence>

        {state.phase === 'listening' && (
          <div className="privacy-chip" role="status">
            <span className="privacy-pulse" />
            Микрофон открыт · канал защищён
          </div>
        )}
      </div>

      {showComposer && (
        <div className="composer-card">
          <label htmlFor="voice-composer">Задача</label>
          <div className="composer-row">
            <input
              id="voice-composer"
              type="text"
              value={composer}
              maxLength={4000}
              placeholder={
                agentMode === 'ask'
                  ? 'Короткий вопрос агенту'
                  : agentMode === 'do'
                    ? 'Что сделать в репо'
                    : 'Что спланировать'
              }
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
              aria-label={MODE_SUBMIT_LABELS[agentMode]}
            >
              <Send size={17} />
            </button>
          </div>
        </div>
      )}

      {(state.phase === 'planning' || state.speakingKind === 'milestone') && (
        <div className="plan-safety" role="status">
          <Check size={17} />
          Агент в работе. Устные вехи и эфир задачи — ниже.
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
              {agentMode === 'ask'
                ? 'Голос отправит вопрос агенту. Approve на запись — только у владельца.'
                : agentMode === 'do'
                  ? 'Голос запустит действие в репо. Approve на риск — только у владельца.'
                  : 'Голос попросит план. Approve на запись — только у владельца.'}
            </p>
            <div className="action-row">
              <button className="secondary-button" type="button" onClick={voice.cancel}>
                <X size={17} /> Отмена
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => voice.confirmSubmit(agentMode)}
                disabled={!state.transcript.trim()}
              >
                <Send size={17} /> {MODE_SUBMIT_LABELS[agentMode]}
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

      <div className="voice-footnote">
        {state.phase === 'speaking'
          ? (
            <>
              <Mic size={14} />
              {state.speakingKind === 'milestone'
                ? 'Орб — прервать статус'
                : 'Орб — прервать брифинг'}
            </>
          )
          : <><MicOff size={14} /> Микрофон молчит, пока не коснёшься орба</>}
      </div>
    </section>
  )
}
