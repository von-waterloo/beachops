import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  Activity,
  Clock3,
  Cloud,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Monitor,
  ShieldCheck,
  Siren,
} from 'lucide-react'
import { AuthScreen } from './components/AuthScreen'
import { VoiceConsole } from './components/VoiceConsole'
import { DashboardPanels, type TabId } from './components/DashboardPanels'
import { ControlRoomHero } from './components/ControlRoomHero'
import { useAuth } from './hooks/useAuth'
import { useDashboard } from './hooks/useDashboard'
import { useJobStream } from './hooks/useJobStream'
import type { AuthenticatedUser } from './lib/passkeys'
import {
  getTelegramInitData,
  haptic,
  initializeTelegram,
  telegramTheme,
} from './lib/telegram'
import { isActiveJobStatus } from './types/api'

const tabs: Array<{ id: TabId; label: string; icon: typeof LayoutDashboard }> = [
  { id: 'voice', label: 'Room', icon: LayoutDashboard },
  { id: 'active', label: 'Active', icon: Activity },
  { id: 'history', label: 'Timeline', icon: Clock3 },
  { id: 'approvals', label: 'Approvals', icon: ShieldCheck },
  { id: 'repositories', label: 'Repos', icon: GitBranch },
]

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    initializeTelegram()
    document.documentElement.dataset.theme = telegramTheme()
  }, [])

  if (!auth.user) {
    return (
      <AuthScreen
        checking={auth.checking}
        busy={auth.busy}
        error={auth.error}
        supported={auth.supported}
        onLogin={() => void auth.login()}
      />
    )
  }

  return (
    <ControlRoom
      user={auth.user}
      busy={auth.busy}
      error={auth.error}
      onRegister={() => void auth.register()}
      onLogout={() => void auth.logout()}
    />
  )
}

interface ControlRoomProps {
  user: AuthenticatedUser
  busy: boolean
  error: string | null
  onRegister: () => void
  onLogout: () => void
}

function ControlRoom({
  user,
  busy,
  error,
  onRegister,
  onLogout,
}: ControlRoomProps) {
  const [tab, setTab] = useState<TabId>('voice')
  const dashboard = useDashboard()
  const [now, setNow] = useState(() => Date.now())

  const activeJob = useMemo(
    () => dashboard.data.jobs.find((job) => isActiveJobStatus(job.status)) ?? null,
    [dashboard.data.jobs],
  )
  const stream = useJobStream(activeJob?.id ?? null, Boolean(activeJob), {
    onTick: () => {
      void dashboard.refresh()
    },
  })

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const selectTab = (next: TabId) => {
    setTab(next)
    haptic('selection')
  }

  const running = dashboard.data.queue?.running ?? dashboard.data.queue?.active ?? 0
  const pending = dashboard.data.queue?.pending ?? dashboard.data.queue?.queued ?? 0
  const workersOnline = dashboard.data.workers?.length ?? 0
  const liveEvents = stream.events.length ? stream.events : dashboard.data.events

  return (
    <div className="app-shell control-room">
      <div className="top-bar">
        <a className="brand" href="#main" aria-label="BeachOps home">
          <span className="brand-glyph">B</span>
          <span>BeachOps</span>
        </a>
        <div className="top-meta">
          {activeJob && (
            <div className="live-badge" title="Active job streaming">
              <span className="live-pulse" />
              Live
            </div>
          )}
          {getTelegramInitData() && user.role === 'owner' && (
            <button
              className="auth-icon-button"
              type="button"
              disabled={busy}
              onClick={onRegister}
              title={user.hasPasskey ? 'Добавить ключ доступа' : 'Включить Face ID / Passkey'}
              aria-label={user.hasPasskey ? 'Добавить ключ доступа' : 'Включить Face ID / Passkey'}
            >
              <Fingerprint size={18} />
              {!user.hasPasskey && <i />}
            </button>
          )}
          {user.authMethod === 'passkey' && (
            <button
              className="auth-icon-button"
              type="button"
              disabled={busy}
              onClick={onLogout}
              title="Выйти"
              aria-label="Выйти"
            >
              <LogOut size={17} />
            </button>
          )}
          <div className="role-badge">
            <span />
            {dashboard.data.role}
          </div>
        </div>
      </div>

      {error && <div className="auth-inline-error">{error}</div>}

      {dashboard.data.panic && (
        <div className="panic-banner" role="alert">
          <Siren size={18} />
          <div>
            <strong>Panic mode is active</strong>
            <span>Writes are locked. Voice cannot change this status.</span>
          </div>
        </div>
      )}

      <ControlRoomHero
        running={running}
        pending={pending}
        workersOnline={workersOnline}
        cloudJobs={dashboard.data.jobs.filter((job) =>
          isActiveJobStatus(job.status) && job.runtime !== 'windows',
        ).length}
      />

      <main id="main">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
          >
            {tab === 'voice' ? (
              <>
                <VoiceConsole
                  activeJob={activeJob}
                  latestEvent={stream.latestEvent}
                />
                <DashboardPanels
                  tab="overview"
                  data={dashboard.data}
                  loading={dashboard.loading}
                  error={dashboard.error ?? stream.error}
                  liveEvents={liveEvents}
                  onRefresh={() => void dashboard.refresh()}
                  onDecision={(approvalId, decision, revision) => {
                    void dashboard.decideApproval(approvalId, decision, revision)
                  }}
                />
              </>
            ) : (
              <DashboardPanels
                tab={tab}
                data={dashboard.data}
                loading={dashboard.loading}
                error={dashboard.error}
                liveEvents={liveEvents}
                onRefresh={() => void dashboard.refresh()}
                onDecision={(approvalId, decision, revision) => {
                  void dashboard.decideApproval(approvalId, decision, revision)
                }}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <section className="worker-strip" aria-label="Execution planes">
        <div className="worker-chip">
          <Cloud size={14} />
          Cloud · live
        </div>
        <div className={`worker-chip ${workersOnline ? 'online' : ''}`}>
          <Monitor size={14} />
          Windows · {workersOnline ? `${workersOnline} online` : 'offline'}
        </div>
        <time className="worker-chip muted">{new Date(now).toLocaleTimeString()}</time>
      </section>

      <nav className="tab-bar" aria-label="Primary navigation">
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
                <Icon size={20} strokeWidth={selected ? 2.4 : 1.8} />
                {item.id === 'approvals' && dashboard.data.approvals.length > 0 && (
                  <i>{Math.min(9, dashboard.data.approvals.length)}</i>
                )}
                {item.id === 'active' && running > 0 && (
                  <i>{Math.min(9, running)}</i>
                )}
              </span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
