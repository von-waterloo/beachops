import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import { isActiveJobStatus, type DashboardSnapshot } from '../types/api'

const emptySnapshot: DashboardSnapshot = {
  jobs: [],
  events: [],
  approvals: [],
  repositories: [],
  agents: [],
  selfImprove: null,
  usage: null,
  panic: false,
  role: 'Operator',
  defaultBranch: 'dev',
  workers: [],
  queue: { pending: 0, running: 0, active: 0, queued: 0, blocked: 0, total: 0 },
}

function normalize(snapshot: Partial<DashboardSnapshot>): DashboardSnapshot {
  const jobs = snapshot.jobs ?? []
  const queue = snapshot.queue
  return {
    ...emptySnapshot,
    ...snapshot,
    jobs,
    events: snapshot.events ?? [],
    approvals: snapshot.approvals ?? [],
    repositories: snapshot.repositories ?? [],
    agents: snapshot.agents ?? [],
    selfImprove: snapshot.selfImprove ?? null,
    workers: snapshot.workers ?? [],
    usage: snapshot.usage ?? null,
    panic: Boolean(snapshot.panic),
    role: snapshot.role ?? 'Operator',
    defaultBranch: snapshot.defaultBranch ?? 'dev',
    queue: {
      pending: queue?.pending ?? queue?.queued ?? 0,
      running: queue?.running ?? queue?.active ?? 0,
      active: queue?.active ?? queue?.running ?? 0,
      queued: queue?.queued ?? queue?.pending ?? 0,
      blocked: queue?.blocked ?? 0,
      total: queue?.total ?? jobs.length,
    },
  }
}

export function useDashboard(pollMs = 15_000) {
  const [data, setData] = useState(emptySnapshot)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const snapshot = await apiFetch<Partial<DashboardSnapshot>>('/api/dashboard')
      setData(normalize(snapshot))
      setError(null)
    } catch {
      setError(navigator.onLine ? 'BeachOps временно недоступен' : 'Нет сети')
    }
    setLoading(false)
  }, [])

  const decideApproval = useCallback(async (
    approvalId: string,
    decision: 'approve' | 'reject' | 'revision',
    revision?: string,
  ) => {
    await apiFetch(`/api/approvals/${approvalId}/decision`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ decision, revision }),
    })
    await refresh()
  }, [refresh])

  const addRepository = useCallback(async (input: {
    url: string
    branch?: string
    makeActive?: boolean
  }) => {
    await apiFetch('/api/repos', {
      method: 'POST',
      body: JSON.stringify({
        url: input.url,
        branch: input.branch || undefined,
        makeActive: input.makeActive ?? true,
      }),
    })
    await refresh()
  }, [refresh])

  const updateRepository = useCallback(async (
    repoId: string,
    input: { branch?: string; makeActive?: boolean },
  ) => {
    await apiFetch(`/api/repos/${repoId}`, {
      method: 'PATCH',
      body: JSON.stringify({
        branch: input.branch,
        makeActive: input.makeActive,
      }),
    })
    await refresh()
  }, [refresh])

  const activateSelfImprove = useCallback(async () => {
    await apiFetch('/api/self-improve/activate', { method: 'POST' })
    await refresh()
  }, [refresh])

  const updateAgent = useCallback(async (
    slotId: string,
    input: {
      runtime?: string
      localPath?: string | null
      preferredWorkerId?: string | null
      makeActive?: boolean
    },
  ) => {
    await apiFetch(`/api/agents/${slotId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    })
    await refresh()
  }, [refresh])

  const submitPrompt = useCallback(async (input: {
    prompt: string
    mode?: 'ask' | 'plan' | 'do'
    slotId?: string
  }) => {
    const result = await apiFetch<{ job: { id: string }; enqueued: boolean; reason?: string }>(
      '/api/prompts',
      {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          prompt: input.prompt,
          mode: input.mode ?? 'ask',
          slotId: input.slotId ? Number(input.slotId) : undefined,
        }),
      },
    )
    await refresh()
    return result
  }, [refresh])

  const hasActive = data.jobs.some((job) => isActiveJobStatus(job.status))
    || (data.queue.running ?? 0) > 0

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, hasActive ? Math.min(pollMs, 4_000) : pollMs)
    return () => window.clearInterval(interval)
  }, [refresh, pollMs, hasActive])

  // Catch up immediately on tab focus / return-from-background instead of
  // waiting out the poll interval, so the plane never looks stale.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    window.addEventListener('online', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
      window.removeEventListener('online', onVisible)
    }
  }, [refresh])

  return {
    data,
    loading,
    error,
    refresh,
    decideApproval,
    addRepository,
    updateRepository,
    activateSelfImprove,
    updateAgent,
    submitPrompt,
  }
}
