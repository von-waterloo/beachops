import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { Event } from '../types/api'

const POLL_MS = 2_000

interface Options {
  onTick?: () => void
}

/**
 * Poll `/api/jobs/{id}/events` every 2s while a job is active.
 * Pass `jobId=null` to idle the stream.
 */
export function useJobStream(
  jobId: string | null,
  enabled = true,
  options: Options = {},
) {
  const [events, setEvents] = useState<Event[]>([])
  const [error, setError] = useState<string | null>(null)
  const onTickRef = useRef(options.onTick)
  onTickRef.current = options.onTick

  const pull = useCallback(async () => {
    if (!jobId || !enabled) {
      setEvents([])
      setError(null)
      return
    }
    try {
      const rows = await apiFetch<Event[]>(`/api/jobs/${jobId}/events`)
      setEvents(rows)
      setError(null)
    } catch {
      setError('Live job stream unavailable')
    }
  }, [jobId, enabled])

  useEffect(() => {
    if (!jobId || !enabled) {
      setEvents([])
      setError(null)
      return undefined
    }
    let cancelled = false
    const tick = async () => {
      await pull()
      if (!cancelled) onTickRef.current?.()
    }
    void tick()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void tick()
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [jobId, enabled, pull])

  const latestEvent = useMemo(() => {
    if (!events.length) return null
    return [...events].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    )[0] ?? null
  }, [events])

  return { events, latestEvent, error, refresh: pull }
}
