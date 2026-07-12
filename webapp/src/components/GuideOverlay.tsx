import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { CircleHelp, X } from 'lucide-react'
import { GUIDE_TIPS, TIP_TOPICS, type GuideTip } from '../lib/guideContent'
import { feedback } from '../lib/feedback'

export type GuideMode = 'help' | null

interface GuideOverlayProps {
  mode: GuideMode
  onClose: () => void
}

const ease = [0.22, 1, 0.36, 1] as const

export function GuideOverlay({ mode, onClose }: GuideOverlayProps) {
  const [topic, setTopic] = useState('Все')
  const [spotlight, setSpotlight] = useState(0)

  useEffect(() => {
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

  const close = () => {
    feedback('tap')
    onClose()
  }

  const tips =
    topic === 'Все'
      ? GUIDE_TIPS
      : GUIDE_TIPS.filter((tip) => tip.topic === topic)

  const featured = GUIDE_TIPS[spotlight] ?? GUIDE_TIPS[0]

  return (
    <AnimatePresence>
      {mode === 'help' && (
        <motion.div
          className="guide-scrim"
          role="dialog"
          aria-modal="true"
          aria-label="Справка BeachOps"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          onClick={close}
        >
          <motion.div
            className="guide-sheet is-help"
            initial={{ y: 36, opacity: 0.85 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ duration: 0.34, ease }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="guide-sheet-handle" aria-hidden="true" />
            <header className="guide-sheet-head">
              <div>
                <p className="eyebrow">Справка</p>
                <h2>Типсы и быстрые ответы</h2>
              </div>
              <button
                type="button"
                className="auth-icon-button"
                aria-label="Закрыть"
                onClick={close}
              >
                <X size={17} />
              </button>
            </header>

            <HelpBody
              featured={featured}
              tips={tips}
              topic={topic}
              onTopic={(next) => {
                feedback('select')
                setTopic(next)
              }}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
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
