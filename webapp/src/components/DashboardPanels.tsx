import { useEffect, useState } from 'react'
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
  LogIn,
  Monitor,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Unplug,
  X,
  Zap,
} from 'lucide-react'
import type {
  AgentSlot,
  AllowedRepository,
  DashboardSnapshot,
  Event,
  Job,
  WorkerNode,
} from '../types/api'
import { isActiveJobStatus } from '../types/api'
import { feedback } from '../lib/feedback'
import {
  disconnectGithub,
  fetchGithubRepos,
  fetchGithubStatus,
  githubOAuthStartUrl,
  pinBranchFor,
  type GithubConnectionStatus,
  type GithubRemoteRepo,
} from '../lib/github'
import {
  fetchCursorHealth,
  type CursorHealthSnapshot,
} from '../lib/cursorHealth'
import {
  matchesRuntimeFilter,
  type RuntimeFilter,
} from '../lib/runtimeFilter'
import {
  eventHeadline,
  eventTypeLabel,
  relativeTimeRu,
  riskLabel,
  runtimeLabel,
  statusLabel,
  statusTone,
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
  onSelectJob?: (jobId: string, runtime?: string | null) => void
  onRefresh: () => void
  onDecision: (approvalId: string, decision: Decision, revision?: string) => Promise<void>
  onAddRepository?: (input: { url: string; branch?: string }) => Promise<void>
  onUpdateRepository?: (repoId: string, input: { branch?: string; makeActive?: boolean }) => Promise<void>
  onSetSelfImprove?: (input: { enabled: boolean; repoUrl?: string | null }) => Promise<void>
  onCreateAgent?: () => Promise<void>
  onUpdateAgent?: (slotId: string, input: { label?: string; makeActive?: boolean }) => Promise<void>
  onDeleteAgent?: (slotId: string) => Promise<void>
  onActivateSelfImprove?: () => Promise<void>
  onSubmitPrompt?: (input: {
    prompt: string
    mode?: 'ask' | 'plan' | 'do'
    slotId?: string
    images?: Array<{ mimeType: string; data: string }>
  }) => Promise<void>
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

function shortGithubRepo(url: string): string {
  return url
    .replace(/^https:\/\/github\.com\//i, '')
    .replace(/\.git$/i, '')
}

function preferredBranch(branches: string[], defaultBranch: string): string {
  const preferred = [defaultBranch, 'dev', 'develop'].find((branch) => branches.includes(branch))
  if (preferred) return preferred
  const nonProtected = branches.find(
    (branch) => !['main', 'master'].includes(branch.toLowerCase()),
  )
  return nonProtected ?? branches[0] ?? defaultBranch
}

function CursorHealthPanel() {
  const [health, setHealth] = useState<CursorHealthSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = async (force = false) => {
    setLoading(true)
    setError(null)
    try {
      setHealth(await fetchCursorHealth(force))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Не удалось проверить Cursor API')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh(false)
  }, [])

  // Silent unless there's an actual problem — no need to show "all good" noise.
  if (!loading && !error && health?.ok) return null

  return (
    <Section eyebrow="Cursor" title="Проблема с доступом">
      <article className="github-connect-card">
        {loading && !health ? null : error ? (
          <p className="muted-hint">{error}</p>
        ) : (
          <>
            <div className="github-connect-topline">
              <strong>Проблема с ключом</strong>
              <button
                type="button"
                className="ghost-link"
                onClick={() => {
                  feedback('tap')
                  void refresh(true).then(() => feedback('success')).catch(() => feedback('error'))
                }}
              >
                <RefreshCw size={14} /> Обновить
              </button>
            </div>
            <ul className="muted-hint" style={{ margin: 0, paddingLeft: '1.1rem' }}>
              {(health?.tokens ?? []).map((token) => (
                <li key={token.tokenKey}>
                  {token.ok ? '✓' : '✗'} {token.tokenKey}
                  {token.identity ? ` · ${token.identity}` : ''}
                  {token.hasActiveRepo === true
                    ? ' · активный repo доступен'
                    : token.hasActiveRepo === false
                      ? ' · активный repo не найден в Cursor'
                      : ''}
                  {token.error ? ` · ${token.error}` : ''}
                </li>
              ))}
            </ul>
          </>
        )}
      </article>
    </Section>
  )
}

function GithubConnectPanel({
  onPin,
  canManage,
}: {
  onPin: (url: string, branch: string) => void
  canManage: boolean
}) {
  const [status, setStatus] = useState<GithubConnectionStatus | null>(null)
  const [repos, setRepos] = useState<GithubRemoteRepo[]>([])
  const [loading, setLoading] = useState(true)
  const [listBusy, setListBusy] = useState(false)
  const [pinning, setPinning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await fetchGithubStatus()
      setStatus(next)
      if (next.connected) {
        setListBusy(true)
        try {
          setRepos(await fetchGithubRepos(1))
        } catch (err: unknown) {
          setRepos([])
          setError(err instanceof Error ? err.message : 'Не удалось загрузить репо GitHub')
        } finally {
          setListBusy(false)
        }
      } else {
        setRepos([])
      }
    } catch {
      setStatus({ configured: false, connected: false, login: null })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  if (!canManage) return null

  return (
    <Section eyebrow="GitHub" title="Войти и выбрать репо">
      <article className="github-connect-card">
        {loading ? (
          <p className="muted-hint"><Loader2 size={14} className="spin-icon" /> Проверяю GitHub…</p>
        ) : !status?.configured ? (
          <p className="muted-hint">
            GitHub OAuth не настроен на сервере. Пока можно вставить URL вручную ниже.
          </p>
        ) : !status.connected ? (
          <>
            <p>
              Войдите в GitHub, выберите репозиторий — он закрепится в BeachOps.
              Cursor всё равно должен иметь доступ к этому репо в своих Settings.
            </p>
            <a
              className="primary-button github-connect-btn"
              href={githubOAuthStartUrl()}
              onClick={() => feedback('tap')}
            >
              <LogIn size={17} />
              Войти через GitHub
            </a>
          </>
        ) : (
          <>
            <div className="github-connect-topline">
              <strong>@{status.login || 'github'}</strong>
              <button
                type="button"
                className="ghost-link"
                onClick={() => {
                  feedback('tap')
                  void disconnectGithub()
                    .then(() => {
                      feedback('success')
                      void refresh()
                    })
                    .catch(() => feedback('error'))
                }}
              >
                <Unplug size={14} /> Отключить
              </button>
            </div>
            {listBusy && (
              <p className="muted-hint"><Loader2 size={14} className="spin-icon" /> Загружаю список…</p>
            )}
            {!listBusy && repos.length === 0 && (
              <p className="muted-hint">Репозиториев не видно — проверьте доступ GitHub.</p>
            )}
            <div className="github-repo-picker">
              {repos.map((repo) => (
                <button
                  key={repo.url}
                  type="button"
                  className="github-repo-option"
                  disabled={pinning === repo.url}
                  onClick={() => {
                    feedback('tap')
                    setPinning(repo.url)
                    const branch = pinBranchFor(repo)
                    onPin(repo.url, branch)
                    window.setTimeout(() => setPinning(null), 1200)
                  }}
                >
                  <span>
                    <strong>{repo.fullName}</strong>
                    <small>
                      {repo.private ? 'private' : 'public'} · ветка {pinBranchFor(repo)}
                    </small>
                  </span>
                  {pinning === repo.url
                    ? <Loader2 size={16} className="spin-icon" />
                    : <Plus size={16} />}
                </button>
              ))}
            </div>
          </>
        )}
        {error && <div className="inline-error" role="alert">{error}</div>}
      </article>
    </Section>
  )
}

function RepoPolicyBanner({
  openMode,
  allowedCount,
}: {
  openMode: boolean
  allowedCount: number
}) {
  return (
    <div className={`locked-notice soft repo-policy-banner${openMode ? '' : ' is-strict'}`}>
      <GitBranch size={18} />
      <div>
        <strong>{openMode ? 'Открытый режим' : 'Только из списка сервера'}</strong>
        <p>
          {openMode
            ? 'Вставьте любой HTTPS GitHub URL и базовую ветку. Запись в main/master запрещена — для работы берите dev или feature.'
            : allowedCount
              ? 'Сервер разрешает только репозитории ниже. Нажмите «Подключить» — URL и ветка подставятся сами.'
              : 'Список разрешённых пуст. Попросите владельца открыть режим или добавить репозитории.'}
        </p>
      </div>
    </div>
  )
}

function AllowedRepoList({
  items,
  connectedUrls,
  defaultBranch,
  busyUrl,
  onConnect,
  onFill,
}: {
  items: AllowedRepository[]
  connectedUrls: Set<string>
  defaultBranch: string
  busyUrl: string | null
  onConnect: (url: string, branch: string) => void
  onFill: (url: string, branch: string) => void
}) {
  if (!items.length) return null
  return (
    <div className="allowed-repo-list" aria-label="Разрешённые репозитории">
      {items.map((item) => {
        const branch = preferredBranch(item.branches, defaultBranch)
        const connected = connectedUrls.has(item.url.toLowerCase())
        const busy = busyUrl === item.url
        return (
          <article className="allowed-repo-card" key={item.url}>
            <div className="allowed-repo-copy">
              <strong>{shortGithubRepo(item.url)}</strong>
              <div className="allowed-branch-chips" role="list">
                {item.branches.map((name) => (
                  <button
                    key={name}
                    type="button"
                    className={`branch-chip${name === branch ? ' is-preferred' : ''}`}
                    role="listitem"
                    onClick={() => {
                      feedback('select')
                      onFill(item.url, name)
                    }}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
            {connected ? (
              <span className="repo-state ready">Уже есть</span>
            ) : (
              <button
                type="button"
                className="allowed-connect-btn"
                disabled={busy}
                onClick={() => {
                  feedback('tap')
                  onConnect(item.url, branch)
                }}
              >
                {busy ? <Loader2 size={16} className="spin-icon" /> : <Plus size={16} />}
                Подключить
              </button>
            )}
          </article>
        )
      })}
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

function RuntimeFilterBar({
  value,
  onChange,
}: {
  value: RuntimeFilter
  onChange?: (filter: RuntimeFilter) => void
}) {
  // Cloud-only product: filter UI removed.
  void value
  void onChange
  return null
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
  const windows = false
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
          {typeof job.totalTokens === 'number'
            ? ` · ${job.totalTokens.toLocaleString('ru-RU')} tok`
            : ''}
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

function SlotCard({
  slot,
  onActivate,
  onDelete,
}: {
  slot: AgentSlot
  onActivate?: () => void
  onDelete?: () => void
}) {
  return (
    <motion.article
      className={`agent-card runtime-cloud${slot.active ? ' is-selected' : ''}${onActivate ? ' is-clickable' : ''}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onActivate}
      role={onActivate ? 'button' : undefined}
      tabIndex={onActivate ? 0 : undefined}
      onKeyDown={(event) => {
        if (!onActivate) return
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onActivate()
        }
      }}
    >
      <div className="agent-mark">
        <Cloud size={18} />
      </div>
      <div className="agent-body">
        <div className="card-topline">
          <span className={`status-pill status-${slot.active ? 'running' : 'ready'}`}>
            <Radio size={12} />
            {slot.active ? 'Активен' : 'Слот'}
          </span>
          {onDelete && (
            <button
              type="button"
              className="ghost-link"
              onClick={(event) => {
                event.stopPropagation()
                onDelete()
              }}
            >
              Удалить
            </button>
          )}
        </div>
        <h2>{slot.label}</h2>
        <p>
          Cloud
          {slot.repository ? ` · ${slot.repository}` : ''}
        </p>
        {slot.cursorUrl ? (
          <a
            className="ghost-link"
            href={slot.cursorUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => {
              event.stopPropagation()
              feedback('tap')
            }}
          >
            <ExternalLink size={14} />
            Открыть в Cursor
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

function SelfImprovePanel({
  data,
  onSetSelfImprove,
}: {
  data: DashboardSnapshot
  onSetSelfImprove?: (input: { enabled: boolean; repoUrl?: string | null }) => Promise<void>
}) {
  const info = data.selfImprove
  const enabled = Boolean(info?.enabled)
  const isOwner = data.role.toLowerCase() === 'owner'
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const activeRepo = data.repositories.find((repo) => repo.active)
  const targetUrl = info?.repoUrl || activeRepo?.url || null

  const toggle = () => {
    if (!onSetSelfImprove || busy || !isOwner) return
    setBusy(true)
    setError(null)
    feedback('tap')
    void onSetSelfImprove({
      enabled: !enabled,
      repoUrl: targetUrl,
    })
      .then(() => feedback('success'))
      .catch((err: unknown) => {
        feedback('error')
        setError(err instanceof Error ? err.message : 'Не удалось переключить')
      })
      .finally(() => setBusy(false))
  }

  return (
    <Section eyebrow="BeachOps" title="Самосовершенствование">
      <article className={`self-improve-card${enabled ? ' is-on' : ''}`}>
        <div className="self-improve-copy">
          <strong>{enabled ? 'Включено' : 'Выключено'}</strong>
          <p>
            {enabled
              ? `Агент может улучшать сам BeachOps (${info?.branches?.join(', ') || 'dev'}). Деплой — только после вашего approve.`
              : 'Когда выключено, задачи идут в обычные репо. Включите, чтобы править этот control plane.'}
          </p>
          {targetUrl ? (
            <p className="muted-hint">Цель: {targetUrl.replace('https://github.com/', '')}</p>
          ) : enabled ? (
            <p className="muted-hint">Сначала сделайте активным репо BeachOps во вкладке «Репо».</p>
          ) : (
            <p className="muted-hint">
              Выключено — обычные задачи идут в активное репо. Для включения закрепите форк BeachOps во вкладке «Репо».
            </p>
          )}
        </div>
        {isOwner ? (
          <button
            type="button"
            className={`self-improve-toggle${enabled ? ' is-on' : ''}`}
            aria-pressed={enabled}
            disabled={busy || (!enabled && !targetUrl)}
            onClick={toggle}
          >
            {busy ? <Loader2 size={16} className="spin-icon" /> : enabled ? 'Выключить' : 'Включить'}
          </button>
        ) : (
          <span className="muted-hint">Только владелец</span>
        )}
      </article>
      {error && <div className="inline-error" role="alert">{error}</div>}
    </Section>
  )
}


function ApprovalsList({
  approvals,
  role,
  pendingIds,
  act,
  compact = false,
}: {
  approvals: DashboardSnapshot['approvals']
  role: string
  pendingIds: Set<string>
  act: (approvalId: string, decision: Decision, revision?: string) => void
  compact?: boolean
}) {
  const items = compact ? approvals.slice(0, 4) : approvals
  return (
    <div className="card-list">
      {items.map((approval) => (
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
          {role.toLowerCase() === 'owner' && (
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
  )
}

function TimelineList({
  events,
  jobsById,
  onSelectJob,
  limit = 40,
}: {
  events: Event[]
  jobsById?: Map<string, Job>
  onSelectJob?: (jobId: string, runtime: string | null | undefined) => void
  limit?: number
}) {
  const items = events.slice(0, limit)
  if (!items.length) {
    return (
      <Empty
        icon={<Archive />}
        title="Лента пуста"
        copy="Здесь появятся статусы прогонов: старт, approve, сбой, готово."
      />
    )
  }
  return (
    <div className="timeline modern-timeline">
      <AnimatePresence initial={false}>
        {items.map((event, index) => {
          const job = event.jobId ? jobsById?.get(event.jobId) : undefined
          const title = event.title || job?.title || null
          const repository = event.repository || job?.repository || null
          const runtime = event.runtime || job?.runtime || null
          const branch = event.branch || job?.branch || null
          const tone = statusTone(event.toStatus || event.summary)
          const headline = eventHeadline(event)
          const metaBits = [
            eventTypeLabel(event.kind),
            repository,
            runtime ? runtimeLabel(runtime) : null,
            branch,
          ].filter(Boolean)
          const selectable = Boolean(onSelectJob && event.jobId)
          const body = (
            <>
              <span className={`timeline-dot tone-${tone}`} />
              <div className="timeline-body">
                <div className="timeline-topline">
                  <span className={`status-pill status-${event.toStatus || event.summary} tone-${tone}`}>
                    {headline}
                  </span>
                  <time>{relativeTimeRu(event.createdAt)}</time>
                </div>
                {title ? <p className="timeline-title">{title}</p> : null}
                <small>{metaBits.join(' · ')}</small>
              </div>
            </>
          )
          return selectable ? (
            <motion.button
              type="button"
              className="timeline-item is-clickable"
              key={event.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(index, 8) * 0.03, ease: [0.22, 1, 0.36, 1] }}
              onClick={() => onSelectJob?.(event.jobId!, runtime)}
            >
              {body}
            </motion.button>
          ) : (
            <motion.article
              className="timeline-item"
              key={event.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(index, 8) * 0.03, ease: [0.22, 1, 0.36, 1] }}
            >
              {body}
            </motion.article>
          )
        })}
      </AnimatePresence>
    </div>
  )
}

function HistoryPanel({
  jobs,
  events,
  runtimeFilter,
  focusedJobId,
  onRuntimeFilterChange,
  onSelectJob,
}: {
  jobs: Job[]
  events: Event[]
  runtimeFilter: RuntimeFilter
  focusedJobId?: string | null
  onRuntimeFilterChange?: (filter: RuntimeFilter, tabHint?: TabId) => void
  onSelectJob?: (jobId: string, runtime: string | null | undefined) => void
}) {
  const jobsById = new Map(jobs.map((job) => [job.id, job]))
  const recentJobs = jobs
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))
    .slice(0, 40)
  const failedCount = recentJobs.filter((job) => job.status === 'failed').length
  const doneCount = recentJobs.filter((job) =>
    ['completed', 'succeeded', 'accepted'].includes(job.status),
  ).length
  const waitingCount = recentJobs.filter((job) =>
    ['awaiting_approval', 'review_required', 'blocked'].includes(job.status),
  ).length

  return (
    <div className="history-feed">
      <RuntimeFilterBar
        value={runtimeFilter}
        onChange={(filter) => onRuntimeFilterChange?.(filter, 'history')}
      />

      <div className="history-stats" aria-label="Сводка ленты">
        <div>
          <strong>{recentJobs.length}</strong>
          <span>Прогонов</span>
        </div>
        <div>
          <strong>{doneCount}</strong>
          <span>Готово</span>
        </div>
        <div>
          <strong>{waitingCount}</strong>
          <span>Ждёт</span>
        </div>
        <div>
          <strong>{failedCount}</strong>
          <span>Сбои</span>
        </div>
      </div>

      <Section eyebrow="Прогоны" title="Недавние задачи">
        {recentJobs.length ? (
          <div className="card-list history-job-list">
            {recentJobs.map((job) => {
              const selected = focusedJobId === job.id
              const tone = statusTone(job.status)
              const className = `work-card history-job-card tone-${tone}${onSelectJob ? ' is-clickable' : ''}${selected ? ' is-selected' : ''}`
              const body = (
                <>
                  <div className="card-topline">
                    <span className={`status-pill status-${job.status} tone-${tone}`}>
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
            icon={<Archive />}
            title="Пока пусто"
            copy="Запустите задачу голосом или из Telegram — она появится здесь."
          />
        )}
      </Section>

      <Section eyebrow="Активность" title="Что менялось">
        <TimelineList
          events={events}
          jobsById={jobsById}
          onSelectJob={onSelectJob}
          limit={24}
        />
      </Section>
    </div>
  )
}

function Overview({
  data,
  pendingIds,
  act,
  runtimeFilter,
  focusedJobId,
  onRuntimeFilterChange,
  onSelectJob,
  onSetSelfImprove,
}: {
  data: DashboardSnapshot
  pendingIds: Set<string>
  act: (approvalId: string, decision: Decision, revision?: string) => void
  runtimeFilter: RuntimeFilter
  focusedJobId?: string | null
  onRuntimeFilterChange?: (filter: RuntimeFilter, tabHint?: TabId) => void
  onSelectJob?: (jobId: string, runtime: string | null | undefined) => void
  onSetSelfImprove?: (input: { enabled: boolean; repoUrl?: string | null }) => Promise<void>
}) {
  const activeJobs = data.jobs
    .filter((job) => isActiveJobStatus(job.status))
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))
  const queuedJobs = data.jobs
    .filter((job) => job.status === 'queued')
    .filter((job) => matchesRuntimeFilter(job.runtime, runtimeFilter))
  const timeline = data.events.slice(0, 12)
  const jobsById = new Map(data.jobs.map((job) => [job.id, job]))

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
          <span>Approve</span>
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
        ) : (
          <Empty
            icon={<Activity />}
            title="Тихий горизонт"
            copy={
              runtimeFilter === 'windows'
                ? 'Нет активных Windows-задач. Переключитесь на Cloud или Все.'
                : runtimeFilter === 'cloud'
                  ? 'Нет активных Cloud-задач. Переключитесь на Windows или Все.'
                  : 'Сейчас нет активных агентов Cloud или Windows.'
            }
          />
        )}
      </Section>

      {(data.agents?.some((slot) => slot.cursorUrl) ?? false) && (
        <Section eyebrow="Cursor" title="Открыть чат на компьютере">
          <div className="agent-grid">
            {data.agents
              .filter((slot) => slot.cursorUrl)
              .map((slot) => (
                <SlotCard key={slot.id} slot={slot} />
              ))}
          </div>
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

      {data.approvals.length > 0 && (
        <Section eyebrow="Approve" title="Ждёт владельца">
          <ApprovalsList
            approvals={data.approvals}
            role={data.role}
            pendingIds={pendingIds}
            act={act}
            compact
          />
        </Section>
      )}

      <SelfImprovePanel data={data} onSetSelfImprove={onSetSelfImprove} />

      <Section eyebrow="Лента" title="События прогонов">
        <TimelineList
          events={timeline}
          jobsById={jobsById}
          onSelectJob={onSelectJob}
          limit={12}
        />
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

const PANEL_TITLES: Record<string, string> = {
  active: 'Активные задачи',
  history: 'Лента',
  approvals: 'Апрувы',
  repositories: 'Репозитории',
  overview: 'Обзор',
}

export function DashboardPanels({
  tab,
  data,
  loading,
  error,
  runtimeFilter = 'all',
  focusedJobId = null,
  onRuntimeFilterChange,
  onSelectJob,
  onRefresh,
  onDecision,
  onAddRepository,
  onUpdateRepository,
  onSetSelfImprove,
  onCreateAgent,
  onUpdateAgent,
  onDeleteAgent,
}: Props) {
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [repoUrl, setRepoUrl] = useState('')
  const [repoBranch, setRepoBranch] = useState(data.defaultBranch || 'dev')
  const [repoBusy, setRepoBusy] = useState(false)
  const [quickBusyUrl, setQuickBusyUrl] = useState<string | null>(null)
  const [repoError, setRepoError] = useState<string | null>(null)
  const [editingBranch, setEditingBranch] = useState<Record<string, string>>({})

  const policy = data.repositoryPolicy
  const openMode = policy?.openMode ?? true
  const allowedRepos = policy?.repositories ?? []
  const connectedUrls = new Set(
    data.repositories
      .map((repo) => repo.url?.toLowerCase())
      .filter((url): url is string => Boolean(url)),
  )

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

  const fillRepoForm = (url: string, branch: string) => {
    setRepoUrl(url)
    setRepoBranch(branch)
    setRepoError(null)
  }

  const connectRepo = (
    url: string,
    branch: string,
    options: { quick?: boolean } = {},
  ) => {
    if (!onAddRepository || repoBusy || quickBusyUrl) return
    if (options.quick) setQuickBusyUrl(url)
    else setRepoBusy(true)
    setRepoError(null)
    void onAddRepository({
      url,
      branch: branch.trim() || data.defaultBranch || 'dev',
    })
      .then(() => {
        setRepoUrl('')
        setRepoBranch(data.defaultBranch || 'dev')
        feedback('success')
      })
      .catch((err: unknown) => {
        feedback('error')
        setRepoError(err instanceof Error ? err.message : 'Не удалось добавить репозиторий')
        if (options.quick) fillRepoForm(url, branch)
      })
      .finally(() => {
        setRepoBusy(false)
        setQuickBusyUrl(null)
      })
  }

  const submitRepo = () => {
    if (!repoUrl.trim()) return
    feedback('tap')
    connectRepo(repoUrl.trim(), repoBranch.trim() || data.defaultBranch || 'dev')
  }

  const filteredActive = data.jobs.filter((job) => isActiveJobStatus(job.status))

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
        <Overview
          data={data}
          pendingIds={pendingIds}
          act={act}
          runtimeFilter={runtimeFilter}
          focusedJobId={focusedJobId}
          onRuntimeFilterChange={onRuntimeFilterChange}
          onSelectJob={onSelectJob}
          onSetSelfImprove={onSetSelfImprove}
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
          ) : (
            <Empty
              icon={<Clock3 />}
              title="Тихий горизонт"
              copy="Сейчас нет активных задач."
            />
          )}
        </>
      )}

      {tab === 'history' && (
        <HistoryPanel
          jobs={data.jobs}
          events={data.events}
          runtimeFilter={runtimeFilter}
          focusedJobId={focusedJobId}
          onRuntimeFilterChange={onRuntimeFilterChange}
          onSelectJob={onSelectJob}
        />
      )}

      {tab === 'approvals' && (
        <>
          <SelfImprovePanel data={data} onSetSelfImprove={onSetSelfImprove} />
          {data.approvals.length > 0 ? (
            <>
              <div className="locked-notice">
                <LockKeyhole size={18} />
                <div>
                  <strong>Ждёт вашего решения</strong>
                  <p>Планы из режима «План» и рискованные действия. Голос сам не одобрит.</p>
                </div>
              </div>
              <ApprovalsList
                approvals={data.approvals}
                role={data.role}
                pendingIds={pendingIds}
                act={act}
              />
            </>
          ) : (
            <div className="locked-notice soft">
              <Zap size={18} />
              <div>
                <strong>Пока пусто — так и должно быть</strong>
                <p>
                  Сюда попадают только планы и высокий риск. Режим «Сделать» идёт без этого шага.
                </p>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'repositories' && (
        <>
          <RepoPolicyBanner openMode={openMode} allowedCount={allowedRepos.length} />

          <CursorHealthPanel />
          <GithubConnectPanel
            canManage={Boolean(onAddRepository)}
            onPin={(url, branch) => connectRepo(url, branch, { quick: true })}
          />

          {!openMode && (
            <AllowedRepoList
              items={allowedRepos}
              connectedUrls={connectedUrls}
              defaultBranch={data.defaultBranch || 'dev'}
              busyUrl={quickBusyUrl}
              onConnect={(url, branch) => connectRepo(url, branch, { quick: true })}
              onFill={fillRepoForm}
            />
          )}

          <form
            className="repo-add-form"
            onSubmit={(event) => {
              event.preventDefault()
              submitRepo()
            }}
          >
            <p className="repo-add-lead">
              {openMode
                ? 'Или вручную: URL → ветка (обычно dev) → Добавить'
                : 'Или вставьте URL вручную — только из списка сервера'}
            </p>
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
                list="repo-branch-suggestions"
              />
              <datalist id="repo-branch-suggestions">
                {[data.defaultBranch || 'dev', 'dev', 'develop', 'main']
                  .filter((value, index, all) => value && all.indexOf(value) === index)
                  .map((value) => (
                    <option key={value} value={value} />
                  ))}
              </datalist>
            </label>
            <button type="submit" disabled={repoBusy || !repoUrl.trim()}>
              {repoBusy ? <Loader2 size={16} className="spin-icon" /> : <Plus size={16} />}
              Добавить
            </button>
          </form>
          {repoError && <div className="inline-error" role="alert">{repoError}</div>}

          {(data.agents?.length ?? 0) > 0 && (
            <Section eyebrow="Агенты" title="Cloud-агенты">
              <div className="agent-grid">
                {data.agents.map((slot) => (
                  <SlotCard
                    key={slot.id}
                    slot={slot}
                    onActivate={
                      onUpdateAgent && !slot.active
                        ? () => {
                            feedback('select')
                            void onUpdateAgent(slot.id, { makeActive: true })
                          }
                        : undefined
                    }
                    onDelete={
                      onDeleteAgent && (data.agents?.length ?? 0) > 1
                        ? () => {
                            if (!window.confirm(`Удалить «${slot.label}»?`)) return
                            void onDeleteAgent(slot.id)
                          }
                        : undefined
                    }
                  />
                ))}
              </div>
              {onCreateAgent && (
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => {
                    feedback('tap')
                    void onCreateAgent()
                  }}
                >
                  <Plus size={16} /> Новый агент
                </button>
              )}
            </Section>
          )}

          {data.repositories.length ? (
            <div className="repo-grid">
              {data.repositories.map((repo) => {
                const draft = editingBranch[repo.id] ?? repo.branch
                return (
                  <motion.article
                    className={`repo-card${repo.active ? ' is-active' : ''}`}
                    key={repo.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <div className="repo-mark"><GitBranch size={18} /></div>
                    <div className="repo-body">
                      <h2>{repo.name}</h2>
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
              title="Подключите репозиторий"
              copy={
                openMode
                  ? 'Без активного репо задачи некуда отправлять. Вставьте HTTPS GitHub URL выше и нажмите «Добавить».'
                  : 'Выберите репо из списка разрешённых или вставьте URL из allowlist — после этого можно говорить агенту.'
              }
            />
          )}
        </>
      )}
    </section>
  )
}
