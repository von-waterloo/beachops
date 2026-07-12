import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  Activity,
  Bot,
  Clock3,
  GitBranch,
  Mic,
  Sparkles,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { AuthScreen } from './components/AuthScreen'
import { VoiceConsole } from './components/VoiceConsole'
import { DashboardPanels, type TabId } from './components/DashboardPanels'
import { AgentControlPanel } from './components/AgentControlPanel'
import { JobChatPanel } from './components/JobChatPanel'
import { useAuth } from './hooks/useAuth'
import { useDashboard } from './hooks/useDashboard'
import { useJobStream } from './hooks/useJobStream'
import type { AuthenticatedUser } from './lib/auth'
import { roleLabel } from './lib/uiCopy'
import { initializeTelegram, applyBeachOpsDarkTheme } from './lib/telegram'
import { feedback, isSoundMuted, setSoundMuted } from './lib/feedback'
import { isActiveJobStatus } from './types/api'

const tabs: Array<{ id: TabId; label: string; icon: typeof Bot }> = [
  { id: 'work', label: 'Работа', icon: Bot },
  { id: 'voice', label: 'Голос', icon: Mic },
  { id: 'history', label: 'Лента', icon: Clock3 },
  { id: 'approvals', label: 'Апрувы', icon: Sparkles },
  { id: 'repositories', label: 'Репо', icon: GitBranch },
]

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    initializeTelegram()
    applyBeachOpsDarkTheme()
  }, [])

  if (!auth.user) {
    return (
      <AuthScreen
        checking={auth.checking}
        busy={auth.busy}
        error={auth.error}
        insideTelegram={auth.insideTelegram}
        onTelegramLogin={(user) => void auth.loginWithTelegram(user)}
        onRetry={() => void auth.refresh()}
      />
    )
  }

  return <ControlRoom user={auth.user} error={auth.error} />
}

interface ControlRoomProps {
  user: AuthenticatedUser
  error: string | null
}

function ControlRoom({ user, error }: ControlRoomProps) {
  const [tab, setTab] = useState<TabId>(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('tab') === 'repos' || params.get('tab') === 'repositories') {
      return 'repositories'
    }
    if (params.get('tab') === 'voice') return 'voice'
    return 'work'
  })
  const [focusedJobId, setFocusedJobId] = useState<string | null>(null)
  const [cursorModelKey, setCursorModelKey] = useState(user.cursorModelKey ?? '')
  const dashboard = useDashboard()
  const [soundMuted, setSoundMutedState] = useState(() => isSoundMuted())

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const github = params.get('github')
    if (!github) return
    if (github === 'connected') feedback('success')
    else if (github === 'denied' || github === 'error') feedback('error')
    params.delete('github')
    params.delete('tab')
    const next = params.toString()
    window.history.replaceState(
      {},
      '',
      `${window.location.pathname}${next ? `?${next}` : ''}${window.location.hash}`,
    )
  }, [])

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
    if (focusedJobId) {
      const focused = activeJobs.find((job) => job.id === focusedJobId)
        ?? dashboard.data.jobs.find((job) => job.id === focusedJobId)
      if (focused) return focused
    }
    return activeJobs[0] ?? null
  }, [activeJobs, dashboard.data.jobs, focusedJobId])

  const stream = useJobStream(activeJob?.id ?? null, Boolean(activeJob), {
    onTick: () => {
      void dashboard.refresh()
    },
  })

  useEffect(() => {
    if (!focusedJobId) return
    const stillThere = dashboard.data.jobs.some((job) => job.id === focusedJobId)
    if (!stillThere) setFocusedJobId(null)
  }, [dashboard.data.jobs, focusedJobId])

  const selectTab = (next: TabId) => {
    setTab(next)
    feedback('select')
  }

  const selectJob = (jobId: string) => {
    setFocusedJobId(jobId)
    setTab('work')
    feedback('select')
  }

  const pending = dashboard.data.queue?.pending ?? dashboard.data.queue?.queued ?? 0
  const running = dashboard.data.queue?.running ?? dashboard.data.queue?.active ?? 0

  return (
    <div className="app-shell control-room">
      <div className="top-bar">
        <a className="brand" href="#main" aria-label="BeachOps home">
          <span className="brand-glyph">B</span>
          <span>BeachOps</span>
        </a>
        <div className="top-meta">
          <button
            className="auth-icon-button"
            type="button"
            onClick={toggleSound}
            title={soundMuted ? 'Включить звук' : 'Выключить звук'}
            aria-label={soundMuted ? 'Включить звук' : 'Выключить звук'}
            aria-pressed={!soundMuted}
          >
            {soundMuted ? <VolumeX size={17} /> : <Volume2 size={17} />}
          </button>
          <div className="role-badge">
            <span />
            {roleLabel(dashboard.data.role)}
          </div>
        </div>
      </div>

      {error && <div className="auth-inline-error">{error}</div>}

      <main id="main">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            {tab === 'work' ? (
              <>
                <AgentControlPanel
                  slots={dashboard.data.agents}
                  role={dashboard.data.role}
                  queuedCount={pending}
                  onUpdateAgent={(slotId, input) => dashboard.updateAgent(slotId, input)}
                  onCreateAgent={() => dashboard.createAgent()}
                  onDeleteAgent={(slotId) => dashboard.deleteAgent(slotId)}
                  onSubmitPrompt={(input) => dashboard.submitPrompt(input)}
                  onJobDispatched={(jobId) => {
                    selectJob(jobId)
                    void dashboard.refresh()
                  }}
                />
                <JobChatPanel
                  jobId={focusedJobId ?? activeJob?.id ?? null}
                  enabled={Boolean(focusedJobId ?? activeJob)}
                />
                {activeJobs.length > 0 && (
                  <section className="queue-compact" aria-label="Очередь">
                    <p className="eyebrow">Сейчас</p>
                    <ul>
                      {activeJobs.slice(0, 5).map((job) => (
                        <li key={job.id}>
                          <button type="button" onClick={() => selectJob(job.id)}>
                            <Activity size={14} />
                            <span>{job.title.slice(0, 48) || job.status}</span>
                            <small>{job.status}</small>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            ) : tab === 'voice' ? (
              <VoiceConsole
                activeJob={activeJob}
                latestEvent={stream.latestEvent}
                cursorModelKey={cursorModelKey || user.cursorModelKey}
                models={user.models ?? []}
                onModelChange={setCursorModelKey}
                onJobStarted={(jobId) => {
                  setFocusedJobId(jobId)
                  void dashboard.refresh()
                }}
              />
            ) : (
              <DashboardPanels
                tab={tab}
                data={dashboard.data}
                loading={dashboard.loading}
                error={dashboard.error}
                focusedJobId={focusedJobId}
                onSelectJob={(jobId) => selectJob(jobId)}
                onRefresh={() => void dashboard.refresh()}
                onDecision={(approvalId, decision, revision) =>
                  dashboard.decideApproval(approvalId, decision, revision)
                }
                onAddRepository={(input) => dashboard.addRepository(input)}
                onUpdateRepository={(repoId, input) =>
                  dashboard.updateRepository(repoId, input)
                }
                onSetSelfImprove={(input) => dashboard.setSelfImprove(input)}
                onCreateAgent={() => dashboard.createAgent()}
                onUpdateAgent={(slotId, input) => dashboard.updateAgent(slotId, input)}
                onDeleteAgent={(slotId) => dashboard.deleteAgent(slotId)}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

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
                <Icon size={20} strokeWidth={selected ? 2.4 : 1.8} />
                {item.id === 'approvals' && dashboard.data.approvals.length > 0 && (
                  <i>{Math.min(9, dashboard.data.approvals.length)}</i>
                )}
                {item.id === 'work' && running > 0 && (
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
