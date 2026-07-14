import { motion } from 'motion/react'
import { CloudLightning, Layers3 } from 'lucide-react'
import type { RuntimeFilter } from '../lib/runtimeFilter'
import { feedback } from '../lib/feedback'

interface Props {
  running: number
  pending: number
  cloudJobs: number
  runtimeFilter: RuntimeFilter
  onSelectFilter: (filter: RuntimeFilter, tabHint?: 'active' | 'voice' | 'agents') => void
}

export function ControlRoomHero({
  running,
  pending,
  cloudJobs,
  runtimeFilter,
  onSelectFilter,
}: Props) {
  const pick = (filter: RuntimeFilter) => {
    feedback('select')
    onSelectFilter(filter, 'active')
  }

  return (
    <section className="control-hero" aria-label="Статус агентов">
      <motion.div
        className="control-hero-glow"
        animate={{ opacity: running > 0 ? [0.4, 0.75, 0.4] : 0.28 }}
        transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
      />
      <div className="control-hero-copy">
        <p className="eyebrow">Ваши агенты</p>
        <h1>Cursor Cloud — один пульт</h1>
        <p>Жмите метрики — откроется нужный срез.</p>
      </div>
      <div className="control-metrics" role="toolbar" aria-label="Фильтр агентов">
        <button
          type="button"
          className={runtimeFilter === 'cloud' ? 'live' : ''}
          onClick={() => pick('cloud')}
          aria-pressed={runtimeFilter === 'cloud'}
        >
          <CloudLightning size={16} />
          <strong>{cloudJobs}</strong>
          <span>Cloud</span>
        </button>
        <button
          type="button"
          onClick={() => pick('all')}
          aria-pressed={runtimeFilter === 'all'}
        >
          <Layers3 size={16} />
          <strong>{pending}</strong>
          <span>Очередь</span>
        </button>
        <button
          type="button"
          className={running ? 'live' : ''}
          onClick={() => pick('all')}
          aria-pressed={runtimeFilter === 'all' && running > 0}
        >
          <strong>{running}</strong>
          <span>В работе</span>
        </button>
      </div>
    </section>
  )
}
