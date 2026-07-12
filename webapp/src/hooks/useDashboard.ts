import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import { isActiveJobStatus, type AgentSlot, type DashboardSnapshot } from '../types/api'

export function mergeAgentSlot(
  slots: AgentSlot[],
  slotId: string,
  updated: AgentSlot,
  makeActive?: boolean,
): AgentSlot[] {
  return slots.map((slot) => {
    if (slot.id !== slotId) {
      return makeActive ? { ...slot, active: false } : slot
    }
    return {
      ...slot,
      ...updated,
      active: makeActive ? true : updated.active ?? slot.active,
    }
  })
}

const emptySnapshot: DashboardSnapshot = {
  jobs: [],
  events: [],
  approvals: [],
  repositories: [],
  agents: [],
  usage: null,
  role: 'Operator',
  defaultBranch: 'dev',
  workers: [],
  queue: { pending: 0, running: 0, active: 0, queued: 0, blocked: 0, total: 0 },
  repositoryPolicy: { openMode: true, repositories: [] },
  selfImprove: { enabled: false, branches: ['dev'], canToggle: true, needsRepo: true },
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
    workers: snapshot.workers ?? [],
    usage: snapshot.usage ?? null,
    role: snapshot.role ?? 'Operator',
    defaultBranch: snapshot.defaultBranch ?? 'dev',
    repositoryPolicy: {
      openMode: snapshot.repositoryPolicy?.openMode ?? true,
      repositories: snapshot.repositoryPolicy?.repositories ?? [],
    },
    selfImprove: {
      enabled: Boolean(snapshot.selfImprove?.enabled),
      repoUrl: snapshot.selfImprove?.repoUrl ?? null,
      branches: snapshot.selfImprove?.branches?.length
        ? snapshot.selfImprove.branches
        : ['dev'],
      canToggle: snapshot.selfImprove?.canToggle ?? true,
      needsRepo: Boolean(snapshot.selfImprove?.needsRepo),
    },
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
  // Drop in-flight /api/dashboard responses that started before a mutation
  // (or a newer refresh). Otherwise a slow poll can overwrite Cloud←Windows.
  const refreshEpoch = useRef(0)

  const refresh = useCallback(async () => {
    const epoch = ++refreshEpoch.current
    try {
      const snapshot = await apiFetch<Partial<DashboardSnapshot>>('/api/dashboard')
      if (epoch !== refreshEpoch.current) return
      setData(normalize(snapshot))
      setError(null)
    } catch {
      if (epoch !== refreshEpoch.current) return
      setError(navigator.onLine ? 'BeachOps временно недоступен' : 'Нет сети')
    }
    if (epoch === refreshEpoch.current) setLoading(false)
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

  const updateAgent = useCallback(async (
    slotId: string,
    input: {
      label?: string
      runtime?: string
      localPath?: string | null
      preferredWorkerId?: string | null
      makeActive?: boolean
    },
  ) => {
    const updated = await apiFetch<AgentSlot>(`/api/agents/${slotId}`, {
      method: 'PATCH',
      body: JSON.stringify({
        label: input.label,
        runtime: input.runtime === 'cloud' ? 'cloud' : undefined,
        makeActive: input.makeActive,
      }),
    })
    refreshEpoch.current += 1
    setData((prev) => ({
      ...prev,
      agents: mergeAgentSlot(prev.agents, slotId, updated, input.makeActive),
    }))
    await refresh()
    setData((prev) => ({
      ...prev,
      agents: mergeAgentSlot(prev.agents, slotId, updated, input.makeActive),
    }))
  }, [refresh])

  const createAgent = useCallback(async (label?: string) => {
    await apiFetch<AgentSlot>('/api/agents', {
      method: 'POST',
      body: JSON.stringify({ label, makeActive: true }),
    })
    await refresh()
  }, [refresh])

  const deleteAgent = useCallback(async (slotId: string) => {
    await apiFetch(`/api/agents/${slotId}`, { method: 'DELETE' })
    await refresh()
  }, [refresh])

  const submitPrompt = useCallback(async (input: {
    prompt: string
    mode?: 'ask' | 'plan' | 'do'
    slotId?: string
    images?: Array<{ mimeType: string; data: string }>
  }) => {
    const result = await apiFetch<{
      job: { id: string }
      enqueued: boolean
      reason?: string
    }>('/api/prompts', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({
        prompt: input.prompt,
        mode: input.mode ?? 'ask',
        slotId: input.slotId,
        images: input.images?.length ? input.images : undefined,
      }),
    })
    await refresh()
    return result
  }, [refresh])

  const setSelfImprove = useCallback(async (input: {
    enabled: boolean
    repoUrl?: string | null
  }) => {
    await apiFetch('/api/self-improve', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({
        enabled: input.enabled,
        repoUrl: input.repoUrl || undefined,
      }),
    })
    await refresh()
  }, [refresh])

  const activateSelfImprove = useCallback(async () => {
    const activeRepo = data.repositories.find((repo) => repo.active)
    await setSelfImprove({ enabled: true, repoUrl: activeRepo?.url ?? null })
  }, [data.repositories, setSelfImprove])

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
    updateAgent,
    createAgent,
    deleteAgent,
    submitPrompt,
    setSelfImprove,
    activateSelfImprove,
  }
}
