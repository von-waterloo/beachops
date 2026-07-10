import { useEffect, useMemo, useState } from 'react'
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
import { useVoiceSession } from '../voice/useVoiceSession'
import type { VoicePhase } from '../voice/state'
import type { Event, Job } from '../types/api'

const phaseLabels: Record<VoicePhase, string> = {
  idle: 'Ready',
  listening: 'Listening',
  transcribing: 'Transcribing',
  confirming: 'Confirm',
  planning: 'Planning',
  speaking: 'Speaking',
  error: 'Needs attention',
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
}

export function VoiceConsole({ activeJob = null, latestEvent = null }: Props) {
  const voice = useVoiceSession()
  const reducedMotion = useReducedMotion()
  const { state } = voice
  const [composer, setComposer] = useState('')
  const [pulse, setPulse] = useState(0.2)

  const active = ['listening', 'transcribing', 'planning', 'speaking'].includes(state.phase)
  const canStart = ['idle', 'error'].includes(state.phase)
  const showComposer = ['idle', 'error'].includes(state.phase)

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
    const runtime = activeJob.runtime === 'windows' ? 'Windows' : 'Cloud'
    const eventBit = latestEvent?.summary ? ` · ${latestEvent.summary}` : ''
    return `${runtime} · ${activeJob.status}${eventBit}`
  }, [activeJob, latestEvent])

  const handleOrb = () => {
    if (state.phase === 'listening') voice.finishListening()
    else if (state.phase === 'speaking') void voice.startListening()
    else if (canStart) void voice.startListening()
  }

  const handleComposer = () => {
    if (voice.submitComposer(composer)) setComposer('')
  }

  return (
    <section className="voice-console" aria-labelledby="voice-heading">
      <header className="voice-heading">
        <div>
          <p className="eyebrow">CONTROL ROOM</p>
          <h1 id="voice-heading">Ask BeachOps</h1>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Open fullscreen"
          onClick={requestTelegramFullscreen}
        >
          <Expand size={18} />
        </button>
      </header>

      <div className={`voice-stage phase-${state.phase} ${active ? 'is-active' : ''}`}>
        {!reducedMotion && (
          <div className="particles" aria-hidden="true">
            {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
          </div>
        )}
        <div className="connection-chip">
          <span className={state.connected ? 'online-dot' : 'offline-dot'} />
          {state.connected ? 'Live' : 'Reconnecting'}
        </div>

        {activeJob && (
          <div className="job-chip" role="status">
            {activeJob.runtime === 'windows' ? <Monitor size={12} /> : <Cloud size={12} />}
            <span>{activeJob.title.slice(0, 42)}</span>
          </div>
        )}

        <motion.button
          type="button"
          className="orb-button"
          aria-label={state.phase === 'listening' ? 'Stop recording' : 'Start voice request'}
          aria-pressed={state.phase === 'listening'}
          onClick={handleOrb}
          animate={{
            scale: 1 + displayEnergy * (state.phase === 'listening' ? 0.12 : 0.06),
          }}
          transition={{ type: 'spring', stiffness: 260, damping: 22 }}
        >
          <span
            className="orb-halo"
            style={{ transform: `scale(${1 + displayEnergy * 0.45})`, opacity: 0.55 + displayEnergy * 0.4 }}
          />
          <span className="orb-core">
            {state.phase === 'listening' ? <Square size={28} fill="currentColor" /> : <Mic size={32} />}
          </span>
        </motion.button>

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
            Microphone on · audio streams securely
          </div>
        )}
      </div>

      {showComposer && (
        <div className="composer-card">
          <label htmlFor="voice-composer">Composer</label>
          <div className="composer-row">
            <input
              id="voice-composer"
              type="text"
              value={composer}
              maxLength={4000}
              placeholder="Type a plan request…"
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
              aria-label="Send plan request"
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
              Transcript
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
              Voice can request a plan. Approval and panic controls stay locked.
            </p>
            <div className="action-row">
              <button className="secondary-button" type="button" onClick={voice.cancel}>
                <X size={17} /> Cancel
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={voice.confirmPlan}
                disabled={!state.transcript.trim()}
              >
                <Send size={17} /> Request plan
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {state.phase === 'error' && (
        <div className="error-actions">
          <button className="secondary-button" type="button" onClick={voice.reset}>
            <RotateCcw size={17} /> Try again
          </button>
        </div>
      )}

      {state.phase === 'planning' && (
        <div className="plan-safety" role="status">
          <Check size={17} /> Planning only — no changes are being approved.
        </div>
      )}

      <div className="voice-footnote">
        {state.phase === 'speaking'
          ? <><Mic size={14} /> Tap the orb to interrupt</>
          : <><MicOff size={14} /> Mic is off until you tap</>}
      </div>
    </section>
  )
}
