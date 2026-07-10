import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, CircleHelp, Sparkles, X } from 'lucide-react'
import {
  GUIDE_TIPS,
  ONBOARDING_STEPS,
  TIP_TOPICS,
  type GuideTip,
} from '../lib/guideContent'
import { feedback } from '../lib/feedback'
import { markOnboardingDone } from '../lib/onboarding'

export type GuideMode = 'onboarding' | 'help' | null

interface GuideOverlayProps {
  mode: GuideMode
  onClose: () => void
}

const ease = [0.22, 1, 0.36, 1] as const

export function GuideOverlay({ mode, onClose }: GuideOverlayProps) {
  const [step, setStep] = useState(0)
  const [topic, setTopic] = useState('Все')
  const [spotlight, setSpotlight] = useState(0)

  useEffect(() => {
    if (mode === 'onboarding') setStep(0)
    if (mode === 'help') {
      setTopic('Все')
      setSpotlight(0)
    }
  }, [mode])

  useEffect(() => {
    if (mode !== 'help') return
    const timer = window.setInterval(() => {
      setSpotlight((prev) => (prev + 1) % GUIDE_TIPS.length)
    }, 4200)
    return () => window.clearInterval(timer)
  }, [mode])

  const finish = (completed: boolean) => {
    if (completed) markOnboardingDone()
    feedback(completed ? 'success' : 'tap')
    onClose()
  }

  const tips =
    topic === 'Все'
      ? GUIDE_TIPS
      : GUIDE_TIPS.filter((tip) => tip.topic === topic)

  const featured = GUIDE_TIPS[spotlight] ?? GUIDE_TIPS[0]

  return (
    <AnimatePresence>
      {mode && (
        <motion.div
          className="guide-scrim"
          role="dialog"
          aria-modal="true"
          aria-label={mode === 'onboarding' ? 'Онбординг BeachOps' : 'Справка BeachOps'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          onClick={() => finish(mode === 'onboarding')}
        >
          <motion.div
            className={`guide-sheet ${mode === 'onboarding' ? 'is-onboarding' : 'is-help'}`}
            initial={{ y: 36, opacity: 0.85 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ duration: 0.34, ease }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="guide-sheet-handle" aria-hidden="true" />
            <header className="guide-sheet-head">
              <div>
                <p className="eyebrow">
                  {mode === 'onboarding' ? 'Знакомство' : 'Справка'}
                </p>
                <h2>
                  {mode === 'onboarding'
                    ? 'Как устроен пульт'
                    : 'Типсы и быстрые ответы'}
                </h2>
              </div>
              <button
                type="button"
                className="auth-icon-button"
                aria-label="Закрыть"
                onClick={() => finish(mode === 'onboarding')}
              >
                <X size={17} />
              </button>
            </header>

            {mode === 'onboarding' ? (
              <OnboardingBody
                step={step}
                onStep={setStep}
                onDone={() => finish(true)}
                onSkip={() => finish(true)}
              />
            ) : (
              <HelpBody
                featured={featured}
                tips={tips}
                topic={topic}
                onTopic={(next) => {
                  feedback('select')
                  setTopic(next)
                }}
              />
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function OnboardingBody({
  step,
  onStep,
  onDone,
  onSkip,
}: {
  step: number
  onStep: (index: number) => void
  onDone: () => void
  onSkip: () => void
}) {
  const current = ONBOARDING_STEPS[step]
  const last = step >= ONBOARDING_STEPS.length - 1

  return (
    <div className="guide-onboarding">
      <div className="guide-progress" aria-hidden="true">
        {ONBOARDING_STEPS.map((item, index) => (
          <span
            key={item.id}
            className={index === step ? 'active' : index < step ? 'done' : ''}
          />
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.article
          key={current.id}
          className="guide-step"
          initial={{ opacity: 0, x: 18 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -14 }}
          transition={{ duration: 0.3, ease }}
        >
          {step === 0 ? (
            <div className="guide-brand-mark" aria-hidden="true">
              <span>B</span>
              <motion.i
                animate={{ scale: [1, 1.08, 1], opacity: [0.45, 0.8, 0.45] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
              />
            </div>
          ) : (
            <motion.div
              className="guide-step-accent"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Sparkles size={14} />
              {current.accent}
            </motion.div>
          )}
          <p className="eyebrow">{current.eyebrow}</p>
          <h3>{current.title}</h3>
          <p>{current.body}</p>
        </motion.article>
      </AnimatePresence>

      <div className="guide-actions">
        <button type="button" className="guide-ghost" onClick={onSkip}>
          Пропустить
        </button>
        <button
          type="button"
          className="guide-primary"
          onClick={() => {
            feedback('tap')
            if (last) onDone()
            else onStep(step + 1)
          }}
        >
          {last ? 'В пульт' : 'Дальше'}
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  )
}

function HelpBody({
  featured,
  tips,
  topic,
  onTopic,
}: {
  featured: GuideTip
  tips: GuideTip[]
  topic: string
  onTopic: (topic: string) => void
}) {
  return (
    <div className="guide-help">
      <AnimatePresence mode="wait">
        <motion.div
          key={featured.id}
          className="guide-spotlight"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.35, ease }}
        >
          <span className="guide-spotlight-label">
            <CircleHelp size={13} />
            Сейчас полезно · {featured.topic}
          </span>
          <strong>{featured.title}</strong>
          <p>{featured.body}</p>
        </motion.div>
      </AnimatePresence>

      <div className="guide-topics" role="tablist" aria-label="Темы справки">
        {TIP_TOPICS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={topic === item}
            className={topic === item ? 'selected' : ''}
            onClick={() => onTopic(item)}
          >
            {item}
          </button>
        ))}
      </div>

      <ul className="guide-tip-list">
        <AnimatePresence initial={false}>
          {tips.map((tip, index) => (
            <motion.li
              key={tip.id}
              layout
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.28, delay: Math.min(index, 6) * 0.04, ease }}
            >
              <span>{tip.topic}</span>
              <strong>{tip.title}</strong>
              <p>{tip.body}</p>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  )
}

interface TipRailProps {
  onOpenHelp: () => void
}

/** Ambient rotating tip under the hero — one job, one line. */
export function TipRail({ onOpenHelp }: TipRailProps) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((prev) => (prev + 1) % GUIDE_TIPS.length)
    }, 5600)
    return () => window.clearInterval(timer)
  }, [])

  const tip = GUIDE_TIPS[index] ?? GUIDE_TIPS[0]

  return (
    <button
      type="button"
      className="tip-rail"
      onClick={() => {
        feedback('select')
        onOpenHelp()
      }}
      aria-label={`Типс: ${tip.title}. Открыть справку`}
    >
      <span className="tip-rail-pulse" aria-hidden="true" />
      <AnimatePresence mode="wait">
        <motion.span
          key={tip.id}
          className="tip-rail-copy"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.32, ease }}
        >
          <em>{tip.topic}</em>
          {tip.title}
        </motion.span>
      </AnimatePresence>
      <CircleHelp size={15} aria-hidden="true" />
    </button>
  )
}
