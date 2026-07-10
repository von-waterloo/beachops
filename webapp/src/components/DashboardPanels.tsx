import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  Activity,
  AlertTriangle,
  Archive,
  Check,
  Clock3,
  Cloud,
  GitBranch,
  HeartPulse,
  Loader2,
  LockKeyhole,
  Monitor,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  X,
} from 'lucide-react'
import type { DashboardSnapshot, Event, Job, WorkerNode } from '../types/api'
import { isActiveJobStatus } from '../types/api'
import { feedback } from '../lib/feedback'

export type TabId = 'voice' | 'active' | 'history' | 'approvals' | 'repositories'

type Decision = 'approve' | 'reject' | 'revision'

interface Props {
  tab: Exclude<TabId, 'voice'> | 'overview'
  data: DashboardSnapshot
  loading: boolean
  error: string | null
  liveEvents?: Event[]
  onRefresh: () => void
  onDecision: (approvalId: string, decision: Decision, revision?: string) => Promise<void>
}

const relativeTime = (value?: string | null) => {
  if (!value) return 'Recently'
  const delta = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.floor(delta / 60_000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return `${Math.floor(minutes / 1440)}d ago`
}

function Empty({ icon, title, copy }: { icon: React.ReactNode; title: string; copy: string }) {
  return (
    <div className="empty-state">
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{copy}</p>
    </div>
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

function AgentCard({ job }: { job: Job }) {
  const windows = job.runtime === 'windows'
  return (
    <motion.article
      className={`agent-card runtime-${windows ? 'windows' : 'cloud'}`}
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="agent-mark">
        {windows ? <Monitor size={18} /> : <Cloud size={18} />}
      </div>
      <div className="agent-body">
        <div className="card-topline">
          <span className={`status-pill status-${job.status}`}>
            <Radio size={12} />
            {job.status}
          </span>
          <time>{relativeTime(job.createdAt)}</time>
        </div>
        <h2>{job.title}</h2>
        <p>
          {windows ? 'Windows worker' : 'Cloud agent'}
          {job.repository ? ` · ${job.repository}` : ''}
        </p>
        <div className="progress-track" aria-label={`${job.progress ?? 0}% complete`}>
          <i style={{ width: `${job.progress ?? statusProgress(job.status)}%` }} />
        </div>
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

function WorkerCard({ worker }: { worker: WorkerNode }) {
  const healthy = worker.status === 'online'
  return (
    <article className={`worker-card ${healthy ? 'is-online' : 'is-offline'}`}>
      <div className="worker-mark">
        <HeartPulse size={16} />
      </div>
      <div>
        <h2>{worker.hostname}</h2>
        <p>
          {worker.platform}
          {' · '}
          {relativeTime(worker.lastHeartbeatAt)}
        </p>
      </div>
      <span className={`repo-state ${healthy ? 'ready' : 'offline'}`}>{worker.status}</span>
    </article>
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
        {pending ? <Loader2 size={15} className="spin-icon" /> : <Check size={15} />} Approve
      </button>
      <button type="button" disabled={pending} onClick={onRevise}>
        <RotateCcw size={15} /> Revise
      </button>
      <button className="danger" type="button" disabled={pending} onClick={onReject}>
        <X size={15} /> Reject
      </button>
    </div>
  )
}

function TimelineList({ events }: { events: Event[] }) {
  if (!events.length) {
    return <Empty icon={<Archive />} title="No history yet" copy="Completed runs will appear here." />
  }
  return (
    <div className="timeline modern-timeline">
      <AnimatePresence initial={false}>
        {events.map((event, index) => (
          <motion.article
            key={event.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(index, 8) * 0.03 }}
          >
            <span className="timeline-dot" />
            <div>
              <p>{event.summary}</p>
              <small>
                {event.kind}
                {event.jobId ? ` · ${event.jobId.slice(0, 8)}` : ''}
                {' · '}
                {relativeTime(event.createdAt)}
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
}: {
  data: DashboardSnapshot
  liveEvents: Event[]
  pendingIds: Set<string>
  act: (approvalId: string, decision: Decision, revision?: string) => void
}) {
  const activeJobs = data.jobs.filter((job) => isActiveJobStatus(job.status))
  const cloudJobs = activeJobs.filter((job) => job.runtime !== 'windows')
  const windowsJobs = activeJobs.filter((job) => job.runtime === 'windows')
  const queuedJobs = data.jobs.filter((job) => job.status === 'queued')
  const timeline = (liveEvents.length ? liveEvents : data.events).slice(0, 12)

  const active = data.queue?.active ?? data.queue?.running ?? 0
  const queuedCount = data.queue?.queued ?? data.queue?.pending ?? 0
  const blocked = data.queue?.blocked ?? 0

  return (
    <div className="control-feed">
      <div className="stats-strip" aria-label="Live queue summary">
        <div>
          <strong>{active}</strong>
          <span>Active</span>
        </div>
        <div>
          <strong>{queuedCount}</strong>
          <span>Queued</span>
        </div>
        <div>
          <strong>{blocked}</strong>
          <span>Blocked</span>
        </div>
        <div>
          <strong>{data.approvals.length}</strong>
          <span>Approvals</span>
        </div>
      </div>

      <Section eyebrow="AGENTS" title="Cloud & Windows">
        {activeJobs.length ? (
          <div className="agent-grid">
            {[...cloudJobs, ...windowsJobs].map((job) => (
              <AgentCard key={job.id} job={job} />
            ))}
          </div>
        ) : (
          <Empty icon={<Activity />} title="Quiet horizon" copy="No Cloud or Windows agents are active." />
        )}
      </Section>

      <Section eyebrow="QUEUE" title="Live queue">
        {queuedJobs.length || activeJobs.length ? (
          <div className="card-list">
            {(queuedJobs.length ? queuedJobs : activeJobs).slice(0, 6).map((job) => (
              <article className="work-card queue-card" key={job.id}>
                <div className="card-topline">
                  <span className={`status-pill status-${job.status}`}>
                    <Radio size={12} />
                    {job.status}
                  </span>
                  <time>{relativeTime(job.createdAt)}</time>
                </div>
                <h2>{job.title}</h2>
                <p>
                  {job.runtime === 'windows' ? 'Windows' : 'Cloud'}
                  {job.repository ? ` · ${job.repository}` : ''}
                  {` · ${job.id.slice(0, 8)}`}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <Empty icon={<Clock3 />} title="Queue clear" copy="Nothing waiting in the durable job queue." />
        )}
      </Section>

      <Section eyebrow="APPROVALS" title="Needs review">
        {data.approvals.length ? (
          <div className="card-list">
            {data.approvals.slice(0, 4).map((approval) => (
              <article className="approval-card" key={approval.id}>
                <div className="card-topline">
                  <span className={`risk risk-${approval.risk}`}>
                    {approval.risk === 'high' ? <AlertTriangle size={13} /> : <ShieldCheck size={13} />}
                    {approval.risk} risk
                  </span>
                  <time>{relativeTime(approval.requestedAt)}</time>
                </div>
                <h2>{approval.title}</h2>
                {data.role.toLowerCase() === 'owner' && (
                  <ApprovalActions
                    pending={pendingIds.has(approval.id)}
                    onApprove={() => act(approval.id, 'approve')}
                    onRevise={() => act(
                      approval.id,
                      'revision',
                      'Review the result and correct issues within the approved scope.',
                    )}
                    onReject={() => act(approval.id, 'reject')}
                  />
                )}
              </article>
            ))}
          </div>
        ) : (
          <Empty icon={<ShieldCheck />} title="All clear" copy="No actions are waiting for review." />
        )}
      </Section>

      <Section eyebrow="TIMELINE" title="Run events">
        <TimelineList events={timeline} />
      </Section>

      <Section eyebrow="WORKERS" title="Worker health">
        {data.workers.length ? (
          <div className="worker-grid">
            {data.workers.map((worker) => (
              <WorkerCard key={worker.id} worker={worker} />
            ))}
          </div>
        ) : (
          <Empty
            icon={<HeartPulse />}
            title="Cloud-only mode"
            copy="No Windows worker heartbeats yet. Cloud agents still run normally."
          />
        )}
      </Section>
    </div>
  )
}

export function DashboardPanels({
  tab,
  data,
  loading,
  error,
  liveEvents = [],
  onRefresh,
  onDecision,
}: Props) {
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())

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
        <Overview data={data} liveEvents={liveEvents} pendingIds={pendingIds} act={act} />
      </section>
    )
  }

  return (
    <section className="panel-page">
      <header className="panel-header">
        <div>
          <p className="eyebrow">BEACHOPS CONTROL</p>
          <h1>{tab === 'active' ? 'Active work' : tab[0].toUpperCase() + tab.slice(1)}</h1>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Refresh"
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
        data.jobs.filter((job) => isActiveJobStatus(job.status)).length ? (
          <div className="agent-grid">
            {data.jobs.filter((job) => isActiveJobStatus(job.status)).map((job) => (
              <AgentCard key={job.id} job={job} />
            ))}
          </div>
        ) : <Empty icon={<Clock3 />} title="Quiet horizon" copy="No jobs are active right now." />
      )}

      {tab === 'history' && <TimelineList events={liveEvents.length ? liveEvents : data.events} />}

      {tab === 'approvals' && (
        <>
          <div className="locked-notice">
            <LockKeyhole size={18} />
            <div>
              <strong>Review-only in Mini App</strong>
              <p>Approve high-risk actions in the secure operator flow.</p>
            </div>
          </div>
          {data.approvals.length ? (
            <div className="card-list">
              {data.approvals.map((approval) => (
                <article className="approval-card" key={approval.id}>
                  <div className="card-topline">
                    <span className={`risk risk-${approval.risk}`}>
                      {approval.risk === 'high' ? <AlertTriangle size={13} /> : <ShieldCheck size={13} />}
                      {approval.risk} risk
                    </span>
                    <time>{relativeTime(approval.requestedAt)}</time>
                  </div>
                  <h2>{approval.title}</h2>
                  <p>{approval.repository ?? 'Protected operation'}</p>
                  {data.role.toLowerCase() === 'owner' && (
                    <ApprovalActions
                      pending={pendingIds.has(approval.id)}
                      onApprove={() => act(approval.id, 'approve')}
                      onRevise={() => act(
                        approval.id,
                        'revision',
                        'Review the result and correct issues within the approved scope.',
                      )}
                      onReject={() => act(approval.id, 'reject')}
                    />
                  )}
                </article>
              ))}
            </div>
          ) : <Empty icon={<ShieldCheck />} title="All clear" copy="No actions are waiting for review." />}
        </>
      )}

      {tab === 'repositories' && (
        data.repositories.length ? (
          <div className="repo-grid">
            {data.repositories.map((repo) => (
              <article className="repo-card" key={repo.id}>
                <div className="repo-mark"><GitBranch size={18} /></div>
                <div>
                  <h2>{repo.name}</h2>
                  <p>{repo.branch} · {relativeTime(repo.lastActivityAt)}</p>
                </div>
                <span className={`repo-state ${repo.status}`}>{repo.status}</span>
              </article>
            ))}
          </div>
        ) : <Empty icon={<GitBranch />} title="No repositories" copy="Connected workspaces will appear here without exposing private URLs." />
      )}
    </section>
  )
}
