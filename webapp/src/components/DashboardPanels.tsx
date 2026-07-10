import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  Activity,
  AlertTriangle,
  Archive,
  Check,
  Clock3,
  Cloud,
  ExternalLink,
  GitBranch,
  HeartPulse,
  Loader2,
  LockKeyhole,
  Monitor,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import type { AgentSlot, DashboardSnapshot, Event, Job, WorkerNode } from '../types/api'
import { isActiveJobStatus } from '../types/api'
import { AgentControlPanel, JobChatPanel } from './AgentControlPanel'
import { feedback } from '../lib/feedback'
import {
  matchesRuntimeFilter,
  RUNTIME_FILTER_LABELS,
  type RuntimeFilter,
} from '../lib/runtimeFilter'
import {
  relativeTimeRu,
  riskLabel,
  runtimeLabel,
  statusLabel,
} from '../lib/uiCopy'

export type TabId = 'voice' | 'active' | 'history' | 'approvals' | 'repositories'

type Decision = 'approve' | 'reject' | 'revision'

interface Props {
  tab: Exclude<TabId, 'voice'> | 'overview'
  data: DashboardSnapshot
  loading: boolean
  error: string | null
  liveEvents?: Event[]
  runtimeFilter?: RuntimeFilter
  focusedJobId?: string | null
  onRuntimeFilterChange?: (filter: RuntimeFilter, tabHint?: TabId) => void
  onSelectJob?: (jobId: string, runtime: string | null | undefined) => void
  onRefresh: () => void
  onDecision: (approvalId: string, decision: Decision, revision?: string) => Promise<void>
  onAddRepository?: (input: { url: string; branch?: string }) => Promise<void>
  onUpdateRepository?: (repoId: string, input: { branch?: string; makeActive?: boolean }) => Promise<void>
  onActivateSelfImprove?: () => Promise<void>
  onUpdateAgent?: (slotId: string, input: {
    runtime?: string
    localPath?: string | null
    preferredWorkerId?: string | null
    makeActive?: boolean
  }) => Promise<void>
  onSubmitPrompt?: (input: {
    prompt: string
    mode?: 'ask' | 'plan' | 'do'
    slotId?: string
  }) => Promise<{ job: { id: string }; enqueued: boolean; reason?: string }>
}

function Empty({ icon, title, copy }: { icon: React.ReactNode; title: string; copy: string }) {
  return (
    <motion.div
      className="empty-state"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{copy}</p>
    </motion.div>
  )
}

function Section({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <section className="cr-section">
      <header className="cr-section-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

function RuntimeFilterBar({
  value,
  onChange,
}: {
  value: RuntimeFilter
  onChange?: (filter: RuntimeFilter) => void
}) {
  if (!onChange) return null
  return (
    <div className="runtime-filter-bar" role="toolbar" aria-label="Фильтр Cloud / Windows">
      {(['all', 'cloud', 'windows'] as const).map((filter) => (
        <button
          key={filter}
          type="button"
          className={value === filter ? 'selected' : ''}
          aria-pressed={value === filter}
          onClick={() => {
            feedback('select')
            onChange(filter)
          }}
        >
          {RUNTIME_FILTER_LABELS[filter]}
        </button>
      ))}
    </div>
  )
}

function AgentCard({
  job,
  selected,
  onSelect,
}: {
  job: Job
  selected?: boolean
  onSelect?: () => void
}) {
  const windows = job.runtime === 'windows'
  const interactive = Boolean(onSelect)
  const openCursor = (event: React.MouseEvent) => {
    event.stopPropagation()
    if (!job.cursorUrl) return
    feedback('tap')
    window.open(job.cursorUrl, '_blank', 'noopener,noreferrer')
  }
  return (
    <motion.article
      className={`agent-card runtime-${windows ? 'windows' : 'cloud'}${selected ? ' is-selected' : ''}${interactive ? ' is-clickable' : ''}`}
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      whileHover={interactive ? { y: -2 } : undefined}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onSelect}
      onKeyDown={interactive ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect?.()
        }
      } : undefined}
    >
      <div className="agent-mark">
        {windows ? <Monitor size={18} /> : <Cloud size={18} />}
      </div>
      <div className="agent-body">
        <div className="card-topline">
          <span className={`status-pill status-${job.status}`}>
            <Radio size={12} />
            {statusLabel(job.status)}
          </span>
          <time>{relativeTimeRu(job.createdAt)}</time>
        </div>
        <h2>{job.title}</h2>
        <p>
          {runtimeLabel(job.runtime)}
          {job.repository ? ` · ${job.repository}` : ''}
          {job.branch ? ` · ${job.branch}` : ''}
        </p>
        {job.cursorUrl && (
          <button
            type="button"
            className="ghost-link"
            onClick={openCursor}
          >
            <ExternalLink size={14} />
            Открыть в Cursor
          </button>
        )}
        <div className="progress-track" aria-label={`${job.progress ?? 0}%`}>
          <i style={{ width: `${job.progress ?? statusProgress(job.status)}%` }} />
        </div>
      </div>
    </motion.article>
  )
}

function SlotCard({ slot }: { slot: AgentSlot }) {
  const windows = slot.runtime === 'windows'
  return (
    <motion.article
      className={`agent-card runtime-${windows ? 'windows' : 'cloud'}${slot.active ? ' is-selected' : ''}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="agent-mark">
        {windows ? <Monitor size={18} /> : <Cloud size={18} />}
      </div>
      <div className="agent-body">
        <div className="card-topline">
          <span className={`status-pill status-${slot.active ? 'running' : 'ready'}`}>
            <Radio size={12} />
            {slot.active ? 'Активен' : 'Слот'}
          </span>
        </div>
        <h2>{slot.label}</h2>
        <p>
          {runtimeLabel(slot.runtime)}
          {slot.repository ? ` · ${slot.repository}` : ''}
        </p>
        {slot.cursorUrl ? (
          <a
            className="ghost-link"
            href={slot.cursorUrl}
            target="_blank"
            rel="noreferrer"
            onClick={() => feedback('tap')}
          >
            <ExternalLink size={14} />
            Открыть чат в Cursor
          </a>
        ) : (
          <p className="muted-hint">Чат появится после первого cloud-run</p>
        )}
      </div>
    </motion.article>
  )
}

function statusProgress(status: Job['status']): number {
  switch (status) {
    case 'queued':
      return 12
    case 'planning':
    case 'approved':
      return 28
    case 'running':
      return 62
    case 'awaiting_approval':
    case 'review_required':
    case 'blocked':
      return 78
    case 'completed':
    case 'accepted':
      return 100
    default:
      return 18
  }
}

function WorkerCard({
  worker,
  onSelect,
}: {
  worker: WorkerNode
  onSelect?: () => void
}) {
  const healthy = worker.status === 'online'
  const interactive = Boolean(onSelect)
  return (
    <motion.article
      className={`worker-card ${healthy ? 'is-online' : 'is-offline'}${interactive ? ' is-clickable' : ''}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onSelect}
      onKeyDown={interactive ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect?.()
        }
      } : undefined}
    >
      <div className="worker-mark">
        <HeartPulse size={16} />
      </div>
      <div>
        <h2>{worker.hostname}</h2>
        <p>
          {worker.platform}
          {' · '}
          {relativeTimeRu(worker.lastHeartbeatAt)}
        </p>
      </div>
      <span className={`repo-state ${healthy ? 'ready' : 'offline'}`}>
        {statusLabel(worker.status)}
      </span>
    </motion.article>
  )
}

function ApprovalActions({
  pending,
  onApprove,
  onRevise,
  onReject,
}: {
  pending: boolean
  onApprove: () => void
  onRevise: () => void
  onReject: () => void
}) {
  return (
    <div className="approval-actions">
      <button type="button" disabled={pending} onClick={onApprove}>
        {pending ? <Loader2 size={15} className="spin-icon" /> : <Check size={15} />}
        Одобрить
      </button>
      <button type="button" disabled={pending} onClick={onRevise}>
        <RotateCcw size={15} /> Доработать
      </button>
      <button className="danger" type="button" disabled={pending} onClick={onReject}>
        <X size={15} /> Отклонить
      </button>
    </div>
  )
}

function TimelineList({ events }: { events: Event[] }) {
  if (!events.length) {
    return (
      <Empty
        icon={<Archive />}
        title="История пуста"
        copy="Завершённые прогоны появятся здесь."
      />
    )
  }
  return (
    <div className="timeline modern-timeline">
      <AnimatePresence initial={false}>
        {events.map((event, index) => (
          <motion.article
            key={event.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(index, 8) * 0.03, ease: [0.22, 1, 0.36, 1] }}
          >
            <span className="timeline-dot" />
            <div>
              <p>{event.summary}</p>
              <small>
                {event.kind}
                {event.jobId ? ` · ${event.jobId.slice(0, 8)}` : ''}
                {' · '}
                {relativeTimeRu(event.createdAt)}
              </small>
            </div>
          </motion.article>
        ))}
      </AnimatePresence>
    </div>
  )
}

function Overview({
  data,
  liveEvents,
  pendingIds,
  act,
  runtimeFilter,
  focusedJobId,
  onRuntimeFilterChange,
  onSelectJob,
  onUpdateAgent,
  onSubmitPrompt,
}: {
  data: DashboardSnapshot
  liveEvents: Event[]
  pendingIds: Set<string>
  act: (approvalId: string, decision: Decision, revision?: string) => void
  runtimeFilter: RuntimeFilter
  focusedJobId?: string | null
  onRuntimeFilterChange?: (filter: RuntimeFilter, tabHint?: TabId) => void
  onSelectJob?: (jobId: string, runtime: string | null | undefined) => void
  onUpdateAgent?: Props['onUpdateAgent']
  onSubmitPrompt?: Props['onSubmitPrompt']
}) {
  const activeJobs = data.jobs
    .filter((job) => isActiveJobStatus(job.status))
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))
  const queuedJobs = data.jobs
    .filter((job) => job.status === 'queued')
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))
  const timeline = (liveEvents.length ? liveEvents : data.events).slice(0, 12)

  const active = data.queue?.active ?? data.queue?.running ?? 0
  const queuedCount = data.queue?.queued ?? data.queue?.pending ?? 0
  const blocked = data.queue?.blocked ?? 0
  const planeTitle =
    runtimeFilter === 'windows'
      ? 'Windows'
      : runtimeFilter === 'cloud'
        ? 'Cloud'
        : 'Cloud и Windows'

  return (
    <div className="control-feed">
      {onUpdateAgent && onSubmitPrompt && (data.agents?.length ?? 0) > 0 && (
        <AgentControlPanel
          slots={data.agents}
          workers={data.workers}
          role={data.role}
          onUpdateAgent={onUpdateAgent}
          onSubmitPrompt={onSubmitPrompt}
          onJobDispatched={(jobId, runtime) => onSelectJob?.(jobId, runtime)}
        />
      )}
      {focusedJobId && <JobChatPanel jobId={focusedJobId} />}

      <div className="stats-strip" aria-label="Сводка очереди">
        <button type="button" onClick={() => onRuntimeFilterChange?.('all', 'active')}>
          <strong>{active}</strong>
          <span>Активно</span>
        </button>
        <button type="button" onClick={() => onRuntimeFilterChange?.('all', 'active')}>
          <strong>{queuedCount}</strong>
          <span>Очередь</span>
        </button>
        <button type="button" onClick={() => onRuntimeFilterChange?.('all', 'approvals')}>
          <strong>{blocked}</strong>
          <span>Блок</span>
        </button>
        <button type="button" onClick={() => onRuntimeFilterChange?.('all', 'approvals')}>
          <strong>{data.approvals.length}</strong>
          <span>Решения</span>
        </button>
      </div>

      <RuntimeFilterBar
        value={runtimeFilter}
        onChange={(filter) => onRuntimeFilterChange?.(filter, 'voice')}
      />

      <Section eyebrow="Агенты" title={planeTitle}>
        {activeJobs.length ? (
          <div className="agent-grid">
            {activeJobs.map((job) => (
              <AgentCard
                key={job.id}
                job={job}
                selected={focusedJobId === job.id}
                onSelect={onSelectJob ? () => onSelectJob(job.id, job.runtime) : undefined}
              />
            ))}
          </div>
        ) : runtimeFilter === 'windows' && data.workers.length > 0 ? (
          <div className="worker-grid">
            {data.workers.map((worker) => (
              <WorkerCard key={worker.id} worker={worker} />
            ))}
            <p className="muted-hint">
              Воркер онлайн, но активных Windows-задач нет. Отправьте задачу боту
              в Telegram или через голос — она появится здесь.
            </p>
          </div>
        ) : (
          <Empty
            icon={<Activity />}
            title="Тихий горизонт"
            copy={
              runtimeFilter === 'windows'
                ? 'Нет активных Windows-задач и онлайн-воркеров.'
                : runtimeFilter === 'cloud'
                  ? 'Нет активных Cloud-задач. Переключитесь на Windows или Все.'
                  : 'Сейчас нет активных агентов Cloud или Windows.'
            }
          />
        )}
      </Section>

      {(data.agents?.length ?? 0) > 0 && (
        <Section eyebrow="Чаты Cursor" title="Агенты">
          <div className="agent-grid">
            {data.agents.map((slot) => (
              <SlotCard key={slot.id} slot={slot} />
            ))}
          </div>
          <p className="muted-hint">
            Полный диалог Cursor открывается снаружи Mini App — встроенный iframe
            Cursor не отдаёт. Здесь — слоты и прямые ссылки.
          </p>
        </Section>
      )}

      <Section eyebrow="Очередь" title="Живая очередь">
        {queuedJobs.length || activeJobs.length ? (
          <div className="card-list">
            {(queuedJobs.length ? queuedJobs : activeJobs).slice(0, 6).map((job) => {
              const selected = focusedJobId === job.id
              const className = `work-card queue-card${onSelectJob ? ' is-clickable' : ''}${selected ? ' is-selected' : ''}`
              const body = (
                <>
                  <div className="card-topline">
                    <span className={`status-pill status-${job.status}`}>
                      <Radio size={12} />
                      {statusLabel(job.status)}
                    </span>
                    <time>{relativeTimeRu(job.createdAt)}</time>
                  </div>
                  <h2>{job.title}</h2>
                  <p>
                    {runtimeLabel(job.runtime)}
                    {job.repository ? ` · ${job.repository}` : ''}
                    {` · ${job.id.slice(0, 8)}`}
                  </p>
                </>
              )
              return onSelectJob ? (
                <button
                  className={className}
                  type="button"
                  key={job.id}
                  onClick={() => onSelectJob(job.id, job.runtime)}
                >
                  {body}
                </button>
              ) : (
                <article className={className} key={job.id}>{body}</article>
              )
            })}
          </div>
        ) : (
          <Empty
            icon={<Clock3 />}
            title="Очередь чиста"
            copy="В durable-очереди ничего не ждёт."
          />
        )}
      </Section>

      <Section eyebrow="Решения" title="Нужен разбор">
        {data.approvals.length ? (
          <div className="card-list">
            {data.approvals.slice(0, 4).map((approval) => (
              <article className="approval-card" key={approval.id}>
                <div className="card-topline">
                  <span className={`risk risk-${approval.risk}`}>
                    {approval.risk === 'high' ? <AlertTriangle size={13} /> : <ShieldCheck size={13} />}
                    {riskLabel(approval.risk)}
                  </span>
                  <time>{relativeTimeRu(approval.requestedAt)}</time>
                </div>
                <h2>{approval.title}</h2>
                {data.role.toLowerCase() === 'owner' && (
                  <ApprovalActions
                    pending={pendingIds.has(approval.id)}
                    onApprove={() => act(approval.id, 'approve')}
                    onRevise={() => act(
                      approval.id,
                      'revision',
                      'Проверь результат и исправь в рамках одобренного scope.',
                    )}
                    onReject={() => act(approval.id, 'reject')}
                  />
                )}
              </article>
            ))}
          </div>
        ) : (
          <Empty
            icon={<ShieldCheck />}
            title="Всё чисто"
            copy="Нет действий, ждущих вашего решения."
          />
        )}
      </Section>

      <Section eyebrow="Лента" title="События прогонов">
        <TimelineList events={timeline} />
      </Section>

      <Section eyebrow="Воркеры" title="Здоровье узлов">
        {data.workers.length ? (
          <div className="worker-grid">
            {data.workers.map((worker) => (
              <WorkerCard
                key={worker.id}
                worker={worker}
                onSelect={
                  onRuntimeFilterChange
                    ? () => onRuntimeFilterChange('windows', 'active')
                    : undefined
                }
              />
            ))}
          </div>
        ) : (
          <Empty
            icon={<HeartPulse />}
            title="Только Cloud"
            copy="Windows-воркеры ещё не стучатся. Cloud-агенты работают как обычно."
          />
        )}
      </Section>
    </div>
  )
}

const PANEL_TITLES: Record<Exclude<TabId, 'voice'>, string> = {
  active: 'Активные задачи',
  history: 'Лента',
  approvals: 'Решения',
  repositories: 'Репозитории',
}

export function DashboardPanels({
  tab,
  data,
  loading,
  error,
  liveEvents = [],
  runtimeFilter = 'all',
  focusedJobId = null,
  onRuntimeFilterChange,
  onSelectJob,
  onRefresh,
  onDecision,
  onAddRepository,
  onUpdateRepository,
  onActivateSelfImprove,
  onUpdateAgent,
  onSubmitPrompt,
}: Props) {
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [repoUrl, setRepoUrl] = useState('')
  const [repoBranch, setRepoBranch] = useState(data.defaultBranch || 'dev')
  const [repoBusy, setRepoBusy] = useState(false)
  const [repoError, setRepoError] = useState<string | null>(null)
  const [selfImproveBusy, setSelfImproveBusy] = useState(false)
  const [editingBranch, setEditingBranch] = useState<Record<string, string>>({})
  const selfImprove = data.selfImprove
  const canActivateSelfImprove = Boolean(
    onActivateSelfImprove
    && selfImprove?.available
    && !selfImprove.active
    && data.role === 'owner',
  )

  const activateSelfImprove = () => {
    if (!onActivateSelfImprove || selfImproveBusy) return
    setSelfImproveBusy(true)
    setRepoError(null)
    feedback('tap')
    void onActivateSelfImprove()
      .then(() => feedback('success'))
      .catch((err: unknown) => {
        setRepoError(err instanceof Error ? err.message : 'Не удалось включить самосовершенствование')
        feedback('error')
      })
      .finally(() => setSelfImproveBusy(false))
  }

  const act = (approvalId: string, decision: Decision, revision?: string) => {
    if (pendingIds.has(approvalId)) return
    feedback('tap')
    setPendingIds((prev) => new Set(prev).add(approvalId))
    void onDecision(approvalId, decision, revision)
      .then(() => feedback(decision === 'reject' ? 'warning' : 'success'))
      .catch(() => feedback('error'))
      .finally(() => {
        setPendingIds((prev) => {
          const next = new Set(prev)
          next.delete(approvalId)
          return next
        })
      })
  }

  const submitRepo = () => {
    if (!onAddRepository || !repoUrl.trim() || repoBusy) return
    setRepoBusy(true)
    setRepoError(null)
    feedback('tap')
    void onAddRepository({
      url: repoUrl.trim(),
      branch: repoBranch.trim() || data.defaultBranch || 'dev',
    })
      .then(() => {
        setRepoUrl('')
        feedback('success')
      })
      .catch((err: unknown) => {
        feedback('error')
        setRepoError(err instanceof Error ? err.message : 'Не удалось добавить репозиторий')
      })
      .finally(() => setRepoBusy(false))
  }

  const filteredActive = data.jobs
    .filter((job) => isActiveJobStatus(job.status))
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))

  if (loading && tab !== 'overview') {
    return (
      <section className="panel-page" aria-busy="true">
        <div className="panel-title skeleton-line" />
        <div className="skeleton-card" />
        <div className="skeleton-card short" />
      </section>
    )
  }

  if (tab === 'overview') {
    return (
      <section className="panel-page overview-page">
        {error && <div className="inline-error" role="alert">{error}</div>}
        {selfImprove?.active ? (
          <div className="self-improve-banner is-active" role="status">
            <Sparkles size={16} />
            <div>
              <strong>Самосовершенствование активно</strong>
              <span>Голос и plan/do идут в репозиторий BeachOps.</span>
            </div>
          </div>
        ) : canActivateSelfImprove ? (
          <button
            type="button"
            className="self-improve-banner"
            onClick={() => {
              feedback('select')
              activateSelfImprove()
            }}
            disabled={selfImproveBusy}
          >
            <Sparkles size={16} />
            <div>
              <strong>Включить самосовершенствование</strong>
              <span>Бот будет читать и править свой репозиторий BeachOps.</span>
            </div>
          </button>
        ) : null}
        <Overview
          data={data}
          liveEvents={liveEvents}
          pendingIds={pendingIds}
          act={act}
          runtimeFilter={runtimeFilter}
          focusedJobId={focusedJobId}
          onRuntimeFilterChange={onRuntimeFilterChange}
          onSelectJob={onSelectJob}
          onUpdateAgent={onUpdateAgent}
          onSubmitPrompt={onSubmitPrompt}
        />
      </section>
    )
  }

  return (
    <section className="panel-page">
      <header className="panel-header">
        <div>
          <p className="eyebrow">BeachOps</p>
          <h1>{PANEL_TITLES[tab]}</h1>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Обновить"
          onClick={() => {
            feedback('tap')
            onRefresh()
          }}
        >
          <RefreshCw size={17} />
        </button>
      </header>

      {error && <div className="inline-error" role="alert">{error}</div>}

      {tab === 'active' && (
        <>
          <RuntimeFilterBar
            value={runtimeFilter}
            onChange={(filter) => onRuntimeFilterChange?.(filter, 'active')}
          />
          {filteredActive.length ? (
            <div className="agent-grid">
              {filteredActive.map((job) => (
                <AgentCard
                  key={job.id}
                  job={job}
                  selected={focusedJobId === job.id}
                  onSelect={onSelectJob ? () => onSelectJob(job.id, job.runtime) : undefined}
                />
              ))}
            </div>
          ) : runtimeFilter === 'windows' && data.workers.length > 0 ? (
            <>
              <div className="worker-grid">
                {data.workers.map((worker) => (
                  <WorkerCard key={worker.id} worker={worker} />
                ))}
              </div>
              <p className="muted-hint">
                Метрика Windows раньше показывала онлайн-воркеры, а не задачи.
                Сейчас здесь узлы онлайн. Задачу создайте в Telegram-боте
                (текст / пересылка / голос) или через Mini App.
              </p>
            </>
          ) : (
            <Empty
              icon={<Clock3 />}
              title="Тихий горизонт"
              copy={
                runtimeFilter === 'windows'
                  ? 'Нет активных Windows-задач и онлайн-воркеров.'
                  : runtimeFilter === 'cloud'
                    ? 'Нет активных Cloud-задач.'
                    : 'Сейчас нет активных задач.'
              }
            />
          )}

          {(data.agents?.length ?? 0) > 0 && (
            <Section eyebrow="Чаты" title="Слоты агентов">
              <div className="agent-grid">
                {data.agents.map((slot) => (
                  <SlotCard key={slot.id} slot={slot} />
                ))}
              </div>
            </Section>
          )}
        </>
      )}

      {tab === 'history' && (
        <TimelineList events={liveEvents.length ? liveEvents : data.events} />
      )}

      {tab === 'approvals' && (
        <>
          <div className="locked-notice">
            <LockKeyhole size={18} />
            <div>
              <strong>Решения владельца</strong>
              <p>Высокий риск подтверждайте осознанно — голос сам не одобрит.</p>
            </div>
          </div>
          {data.approvals.length ? (
            <div className="card-list">
              {data.approvals.map((approval) => (
                <article className="approval-card" key={approval.id}>
                  <div className="card-topline">
                    <span className={`risk risk-${approval.risk}`}>
                      {approval.risk === 'high' ? <AlertTriangle size={13} /> : <ShieldCheck size={13} />}
                      {riskLabel(approval.risk)}
                    </span>
                    <time>{relativeTimeRu(approval.requestedAt)}</time>
                  </div>
                  <h2>{approval.title}</h2>
                  <p>{approval.repository ?? 'Защищённая операция'}</p>
                  {data.role.toLowerCase() === 'owner' && (
                    <ApprovalActions
                      pending={pendingIds.has(approval.id)}
                      onApprove={() => act(approval.id, 'approve')}
                      onRevise={() => act(
                        approval.id,
                        'revision',
                        'Проверь результат и исправь в рамках одобренного scope.',
                      )}
                      onReject={() => act(approval.id, 'reject')}
                    />
                  )}
                </article>
              ))}
            </div>
          ) : (
            <Empty
              icon={<ShieldCheck />}
              title="Всё чисто"
              copy="Нет действий, ждущих вашего решения."
            />
          )}
        </>
      )}

      {tab === 'repositories' && (
        <>
          <article className={`self-improve-card${selfImprove?.active ? ' is-active' : ''}`}>
            <div className="self-improve-mark">
              <Sparkles size={18} />
            </div>
            <div className="self-improve-body">
              <p className="eyebrow">Режим BeachOps</p>
              <h2>Самосовершенствование</h2>
              <p>
                {selfImprove?.active
                  ? 'Активно: бот читает и правит свой репозиторий BeachOps (plan/do с усиленным safety-промптом).'
                  : selfImprove?.available
                    ? 'Подключите форк BeachOps одним нажатием — дальше голос и /do работают уже по самому боту.'
                    : 'На этом инстансе режим выключен (SELF_IMPROVE_ENABLED). Owner включает его в .env сервера.'}
              </p>
              {selfImprove?.repoUrl && (
                <small className="self-improve-meta">
                  {selfImprove.repoUrl}
                  {selfImprove.branches?.length
                    ? ` · ${selfImprove.branches.join(', ')}`
                    : ''}
                </small>
              )}
              <div className="self-improve-actions">
                {selfImprove?.active ? (
                  <span className="repo-state ready">Активен</span>
                ) : canActivateSelfImprove ? (
                  <button
                    type="button"
                    className="primary-button"
                    disabled={selfImproveBusy}
                    onClick={activateSelfImprove}
                  >
                    {selfImproveBusy
                      ? <Loader2 size={16} className="spin-icon" />
                      : <Sparkles size={16} />}
                    Включить
                  </button>
                ) : selfImprove?.linked ? (
                  <button
                    type="button"
                    className="primary-button"
                    disabled={!onUpdateRepository || selfImproveBusy}
                    onClick={() => {
                      const repo = data.repositories.find((item) => item.selfImprove)
                      if (!repo || !onUpdateRepository) return
                      setSelfImproveBusy(true)
                      feedback('tap')
                      void onUpdateRepository(repo.id, { makeActive: true })
                        .then(() => feedback('success'))
                        .catch(() => feedback('error'))
                        .finally(() => setSelfImproveBusy(false))
                    }}
                  >
                    Сделать активным
                  </button>
                ) : null}
              </div>
            </div>
          </article>

          <form
            className="repo-add-form"
            onSubmit={(event) => {
              event.preventDefault()
              submitRepo()
            }}
          >
            <label>
              <span>GitHub URL</span>
              <input
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/org/repo"
                autoComplete="off"
                inputMode="url"
              />
            </label>
            <label>
              <span>Базовая ветка</span>
              <input
                value={repoBranch}
                onChange={(event) => setRepoBranch(event.target.value)}
                placeholder={data.defaultBranch || 'dev'}
                autoComplete="off"
              />
            </label>
            <button type="submit" disabled={repoBusy || !repoUrl.trim()}>
              {repoBusy ? <Loader2 size={16} className="spin-icon" /> : <Plus size={16} />}
              Добавить
            </button>
          </form>
          {repoError && <div className="inline-error" role="alert">{repoError}</div>}

          {(data.agents?.length ?? 0) > 0 && (
            <Section eyebrow="Чаты" title="Cloud-агенты">
              <div className="agent-grid">
                {data.agents.map((slot) => (
                  <SlotCard key={slot.id} slot={slot} />
                ))}
              </div>
            </Section>
          )}

          {data.repositories.length ? (
            <div className="repo-grid">
              {data.repositories.map((repo) => {
                const draft = editingBranch[repo.id] ?? repo.branch
                return (
                  <motion.article
                    className={`repo-card${repo.active ? ' is-active' : ''}${repo.selfImprove ? ' is-self-improve' : ''}`}
                    key={repo.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <div className="repo-mark">
                      {repo.selfImprove ? <Sparkles size={18} /> : <GitBranch size={18} />}
                    </div>
                    <div className="repo-body">
                      <h2>
                        {repo.name}
                        {repo.selfImprove ? <i className="self-improve-pill">self</i> : null}
                      </h2>
                      <p>{repo.url ?? repo.name}</p>
                      <div className="repo-branch-row">
                        <input
                          value={draft}
                          aria-label={`Базовая ветка ${repo.name}`}
                          onChange={(event) => setEditingBranch((prev) => ({
                            ...prev,
                            [repo.id]: event.target.value,
                          }))}
                        />
                        <button
                          type="button"
                          disabled={!onUpdateRepository || draft === repo.branch}
                          onClick={() => {
                            if (!onUpdateRepository || !draft.trim()) return
                            feedback('tap')
                            void onUpdateRepository(repo.id, { branch: draft.trim() })
                              .then(() => feedback('success'))
                              .catch(() => feedback('error'))
                          }}
                        >
                          Сохранить
                        </button>
                      </div>
                      <div className="repo-actions">
                        {repo.active ? (
                          <span className="repo-state ready">Активен</span>
                        ) : (
                          <button
                            type="button"
                            className="ghost-link"
                            disabled={!onUpdateRepository}
                            onClick={() => {
                              if (!onUpdateRepository) return
                              feedback('tap')
                              void onUpdateRepository(repo.id, { makeActive: true })
                                .then(() => feedback('success'))
                                .catch(() => feedback('error'))
                            }}
                          >
                            Сделать активным
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.article>
                )
              })}
            </div>
          ) : (
            <Empty
              icon={<GitBranch />}
              title="Нет репозиториев"
              copy="Добавьте GitHub URL и базовую ветку — дальше /do работает прямо на ней."
            />
          )}
        </>
      )}
    </section>
  )
}
