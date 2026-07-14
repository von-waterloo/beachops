import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import {
  Activity,
  Bot,
  CircleHelp,
  Cloud,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Siren,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { AuthScreen } from './components/AuthScreen'
import { VoiceConsole } from './components/VoiceConsole'
import { DashboardPanels, type TabId } from './components/DashboardPanels'
import { ControlRoomHero } from './components/ControlRoomHero'
import { GuideOverlay, TipRail, type GuideMode } from './components/GuideOverlay'
import { useAuth } from './hooks/useAuth'
import { useDashboard } from './hooks/useDashboard'
import { useJobStream } from './hooks/useJobStream'
import type { AuthenticatedUser } from './lib/passkeys'
import {
  initializeTelegram,
} from './lib/telegram'
import { feedback, isSoundMuted, setSoundMuted } from './lib/feedback'
import {
  matchesRuntimeFilter,
  type RuntimeFilter,
} from './lib/runtimeFilter'
import { isActiveJobStatus } from './types/api'

const tabs: Array<{ id: TabId; label: string; icon: typeof LayoutDashboard }> = [
  { id: 'voice', label: 'Голос', icon: LayoutDashboard },
  { id: 'agents', label: 'Агенты', icon: Bot },
  { id: 'active', label: 'Актив', icon: Activity },
  { id: 'repositories', label: 'Репо', icon: GitBranch },
]

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    initializeTelegram()
  }, [])

  if (!auth.user) {
    return (
      <AuthScreen
        checking={auth.checking}
        busy={auth.busy}
        error={auth.error}
        insideTelegram={auth.insideTelegram}
        onTelegramLogin={auth.loginWithTelegram}
        onRetry={() => void auth.refresh()}
      />
    )
  }

  return (
    <ControlRoom
      user={auth.user}
      busy={auth.busy}
      error={auth.error}
      onLogout={() => void auth.logout()}
    />
  )
}

interface ControlRoomProps {
  user: AuthenticatedUser
  busy: boolean
  error: string | null
  onLogout: () => void
}

function ControlRoom({
  user,
  busy,
  error,
  onLogout,
}: ControlRoomProps) {
  const [tab, setTab] = useState<TabId>('voice')
  const [runtimeFilter, setRuntimeFilter] = useState<RuntimeFilter>('all')
  const [focusedJobId, setFocusedJobId] = useState<string | null>(null)
  const [cursorModelKey, setCursorModelKey] = useState(user.cursorModelKey ?? '')
  const [guideMode, setGuideMode] = useState<GuideMode>(null)
  const dashboard = useDashboard()
  const [now, setNow] = useState(() => Date.now())
  const [soundMuted, setSoundMutedState] = useState(() => isSoundMuted())

  const toggleSound = () => {
    const next = !soundMuted
    setSoundMuted(next)
    setSoundMutedState(next)
    feedback('tap')
  }

  const activeJobs = useMemo(
    () => dashboard.data.jobs.filter((job) => isActiveJobStatus(job.status)),
    [dashboard.data.jobs],
  )

  const activeJob = useMemo(() => {
    const scoped = activeJobs.filter((job) =>
      matchesRuntimeFilter(job.runtime, runtimeFilter),
    )
    const pool = scoped.length ? scoped : activeJobs
    if (focusedJobId) {
      const focused = pool.find((job) => job.id === focusedJobId)
        ?? activeJobs.find((job) => job.id === focusedJobId)
      if (focused) return focused
    }
    return pool[0] ?? null
  }, [activeJobs, focusedJobId, runtimeFilter])

  const stream = useJobStream(activeJob?.id ?? null, Boolean(activeJob))

  useEffect(() => {
    if (!focusedJobId) return
    const stillThere = dashboard.data.jobs.some(
      (job) => job.id === focusedJobId && isActiveJobStatus(job.status),
    )
    if (!stillThere) setFocusedJobId(null)
  }, [dashboard.data.jobs, focusedJobId])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const selectTab = (next: TabId) => {
    setTab(next)
    feedback('select')
  }

  const selectFilter = (filter: RuntimeFilter, tabHint: TabId = 'active') => {
    setRuntimeFilter(filter)
    setFocusedJobId(null)
    setTab(tabHint)
    feedback('select')
  }

  const selectJob = (jobId: string) => {
    setFocusedJobId(jobId)
    setRuntimeFilter('all')
    setTab('voice')
    feedback('select')
  }

  const running = dashboard.data.queue?.running ?? dashboard.data.queue?.active ?? 0
  const pending = dashboard.data.queue?.pending ?? dashboard.data.queue?.queued ?? 0
  const cloudJobs = activeJobs.length
  const liveEvents = stream.events.length ? stream.events : dashboard.data.events
  const canLogout = user.authMethod === 'passkey'
    || user.authMethod === 'session'
    || user.authMethod === 'telegram_login'

  return (
    <div className="app-shell control-room">
      <div className="top-bar">
        <a className="brand" href="#main" aria-label="BeachOps home">
          <span className="brand-glyph">B</span>
          <span>BeachOps</span>
          <span className="app-badge" title="BeachOps control plane">
            <i aria-hidden="true" />
            App
          </span>
        </a>
        <div className="top-meta">
          <button
            className="auth-icon-button"
            type="button"
            onClick={() => {
              feedback('tap')
              setGuideMode('help')
            }}
            title="Справка и типсы"
            aria-label="Открыть справку"
          >
            <CircleHelp size={17} />
          </button>
          <button
            className="auth-icon-button"
            type="button"
            onClick={toggleSound}
            title={soundMuted ? 'Включить звук и вибрацию' : 'Выключить звук и вибрацию'}
            aria-label={soundMuted ? 'Включить звук и вибрацию' : 'Выключить звук и вибрацию'}
            aria-pressed={!soundMuted}
          >
            {soundMuted ? <VolumeX size={17} /> : <Volume2 size={17} />}
          </button>
          {canLogout && (
            <button
              className="auth-icon-button"
              type="button"
              disabled={busy}
              onClick={() => {
                feedback('tap')
                onLogout()
              }}
              title="Выйти"
              aria-label="Выйти"
            >
              <LogOut size={17} />
            </button>
          )}
        </div>
      </div>

      {error && <div className="auth-inline-error">{error}</div>}

      {dashboard.data.panic && (
        <div className="panic-banner" role="alert">
          <Siren size={18} />
          <div>
            <strong>Panic включён</strong>
            <span>Запись в репо заблокирована. Голос это не снимет.</span>
          </div>
        </div>
      )}

      <ControlRoomHero
        running={running}
        pending={pending}
        cloudJobs={cloudJobs}
        runtimeFilter={runtimeFilter}
        onSelectFilter={selectFilter}
      />

      {tab !== 'voice' && (
        <TipRail onOpenHelp={() => setGuideMode('help')} />
      )}

      <main id="main">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            {tab === 'voice' ? (
              <VoiceConsole
                activeJob={activeJob}
                latestEvent={stream.latestEvent}
                agents={dashboard.data.agents}
                activeJobs={activeJobs}
                cursorModelKey={cursorModelKey || user.cursorModelKey}
                models={user.models ?? []}
                onModelChange={setCursorModelKey}
                onActivateAgent={(slotId) =>
                  dashboard.updateAgent(slotId, { makeActive: true })
                }
                onSubmitPrompt={async (input) => {
                  const result = await dashboard.submitPrompt(input)
                  if (result.enqueued) selectJob(result.job.id)
                  return result
                }}
              />
            ) : (
              <DashboardPanels
                tab={tab}
                data={dashboard.data}
                loading={dashboard.loading}
                error={dashboard.error}
                liveEvents={liveEvents}
                runtimeFilter={runtimeFilter}
                focusedJobId={focusedJobId}
                onRuntimeFilterChange={selectFilter}
                onSelectJob={selectJob}
                onRefresh={() => void dashboard.refresh()}
                onDecision={(approvalId, decision, revision) =>
                  dashboard.decideApproval(approvalId, decision, revision)
                }
                onAddRepository={(input) => dashboard.addRepository(input)}
                onUpdateRepository={(repoId, input) =>
                  dashboard.updateRepository(repoId, input)
                }
                onSetSelfImprove={(input) => dashboard.setSelfImprove(input)}
                onUpdateAgent={(slotId, input) => dashboard.updateAgent(slotId, input)}
                onCreateAgent={() => dashboard.createAgent()}
                onDeleteAgent={(slotId) => dashboard.deleteAgent(slotId)}
                onSubmitPrompt={async (input) => dashboard.submitPrompt(input)}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <section className="worker-strip" aria-label="Статус Cloud">
        <button
          type="button"
          className={`worker-chip ${runtimeFilter === 'cloud' ? 'selected' : ''}`}
          aria-pressed={runtimeFilter === 'cloud'}
          onClick={() => selectFilter('cloud', 'active')}
        >
          <Cloud size={14} />
          Cloud · {running > 0 ? 'в эфире' : 'на посту'}
        </button>
        <button
          type="button"
          className={`worker-chip ${runtimeFilter === 'all' ? 'selected' : ''}`}
          aria-pressed={runtimeFilter === 'all'}
          onClick={() => selectFilter('all', 'active')}
        >
          Все задачи
        </button>
        <time className="worker-chip muted">
          {new Date(now).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
        </time>
      </section>

      <LayoutGroup id="main-tabs">
        <nav className="tab-bar" aria-label="Основная навигация">
        {tabs.map((item) => {
          const Icon = item.icon
          const selected = item.id === tab
          return (
            <button
              type="button"
              key={item.id}
              className={selected ? 'selected' : ''}
              aria-current={selected ? 'page' : undefined}
              onClick={() => selectTab(item.id)}
            >
              <span className="tab-icon">
                {selected && (
                  <motion.span
                    layoutId="tab-indicator"
                    className="tab-indicator"
                    transition={{ type: 'spring', stiffness: 520, damping: 34 }}
                    aria-hidden="true"
                  />
                )}
                <Icon size={20} strokeWidth={selected ? 2.4 : 1.8} />
                {item.id === 'active' && running > 0 && (
                  <i>{Math.min(9, running)}</i>
                )}
              </span>
              <span>{item.label}</span>
            </button>
          )
        })}
        </nav>
      </LayoutGroup>

      <GuideOverlay mode={guideMode} onClose={() => setGuideMode(null)} />
    </div>
  )
}
