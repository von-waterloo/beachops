import { motion } from 'motion/react'
import { CloudLightning, Layers3, MonitorSmartphone } from 'lucide-react'

interface Props {
  running: number
  pending: number
  workersOnline: number
  cloudJobs: number
}

export function ControlRoomHero({ running, pending, workersOnline, cloudJobs }: Props) {
  return (
    <section className="control-hero" aria-label="Control room status">
      <motion.div
        className="control-hero-glow"
        animate={{ opacity: running > 0 ? [0.35, 0.7, 0.35] : 0.25 }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <div className="control-hero-copy">
        <p className="eyebrow">WAR ROOM</p>
        <h1>Cloud и Windows — под одним командованием</h1>
        <p>Очередь, durable jobs, голос. Без лишнего шума.</p>
      </div>
      <div className="control-metrics">
        <article>
          <CloudLightning size={16} />
          <strong>{cloudJobs}</strong>
          <span>Cloud</span>
        </article>
        <article>
          <Layers3 size={16} />
          <strong>{pending}</strong>
          <span>Queued</span>
        </article>
        <article>
          <MonitorSmartphone size={16} />
          <strong>{workersOnline}</strong>
          <span>Windows</span>
        </article>
        <article className={running ? 'live' : ''}>
          <strong>{running}</strong>
          <span>Running</span>
        </article>
      </div>
    </section>
  )
}
