import { motion } from 'motion/react'
import { Activity, CloudLightning, Layers3, MonitorSmartphone } from 'lucide-react'
import type { RuntimeFilter } from '../lib/runtimeFilter'
import { feedback } from '../lib/feedback'

interface Props {
  running: number
  pending: number
  workersOnline: number
  cloudJobs: number
  runtimeFilter: RuntimeFilter
  onSelectFilter: (filter: RuntimeFilter, tabHint?: 'active' | 'voice' | 'approvals') => void
}

export function ControlRoomHero({
  running,
  pending,
  workersOnline,
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
        animate={{ opacity: running > 0 ? [0.35, 0.7, 0.35] : 0.22 }}
        transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
      />
      <div className="control-hero-copy">
        <p className="eyebrow">Ваши агенты</p>
        <h2>Cloud и Windows — все рядом</h2>
        <p>Жмите метрики — откроется нужный срез.</p>
      </div>
      <div className="control-metrics" role="toolbar" aria-label="Фильтр агентов">
        <button
          type="button"
          className={runtimeFilter === 'cloud' ? 'live' : ''}
          onClick={() => pick('cloud')}
          aria-pressed={runtimeFilter === 'cloud'}
        >
          <CloudLightning size={15} aria-hidden="true" />
          <strong>{cloudJobs}</strong>
          <span>Cloud</span>
        </button>
        <button
          type="button"
          className={runtimeFilter === 'all' && pending > 0 ? 'live' : ''}
          onClick={() => pick('all')}
          aria-pressed={runtimeFilter === 'all'}
        >
          <Layers3 size={15} aria-hidden="true" />
          <strong>{pending}</strong>
          <span>Очередь</span>
        </button>
        <button
          type="button"
          className={runtimeFilter === 'windows' ? 'live' : ''}
          onClick={() => pick('windows')}
          aria-pressed={runtimeFilter === 'windows'}
        >
          <MonitorSmartphone size={15} aria-hidden="true" />
          <strong>{workersOnline}</strong>
          <span>Windows</span>
        </button>
        <button
          type="button"
          className={running ? 'live' : ''}
          onClick={() => pick('all')}
          aria-pressed={runtimeFilter === 'all' && running > 0}
        >
          <Activity size={15} aria-hidden="true" />
          <strong>{running}</strong>
          <span>В работе</span>
        </button>
      </div>
    </section>
  )
}
