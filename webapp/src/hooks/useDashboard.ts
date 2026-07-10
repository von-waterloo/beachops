import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import { isActiveJobStatus, type DashboardSnapshot } from '../types/api'

const emptySnapshot: DashboardSnapshot = {
  jobs: [],
  events: [],
  approvals: [],
  repositories: [],
  usage: null,
  panic: false,
  role: 'Operator',
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
    workers: snapshot.workers ?? [],
    usage: snapshot.usage ?? null,
    panic: Boolean(snapshot.panic),
    role: snapshot.role ?? 'Operator',
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
      setError(navigator.onLine ? 'Dashboard is temporarily unavailable' : 'You are offline')
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

  const hasActive = data.jobs.some((job) => isActiveJobStatus(job.status))
    || (data.queue.running ?? 0) > 0

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, hasActive ? Math.min(pollMs, 5_000) : pollMs)
    return () => window.clearInterval(interval)
  }, [refresh, pollMs, hasActive])

  return { data, loading, error, refresh, decideApproval }
}
