import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { JobStreamSnapshot } from '../types/api'

const POLL_MS = 2_000

/**
 * Poll `/api/jobs/{id}/stream` every 2s while a job chat is open.
 * Pass `jobId=null` to idle the poll.
 */
export function useJobTranscript(jobId: string | null, enabled = true, pollMs = POLL_MS) {
  const [snapshot, setSnapshot] = useState<JobStreamSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const jobIdRef = useRef(jobId)
  jobIdRef.current = jobId

  const pull = useCallback(async () => {
    const currentJobId = jobIdRef.current
    if (!currentJobId || !enabled) {
      setSnapshot(null)
      setError(null)
      return
    }
    try {
      const next = await apiFetch<JobStreamSnapshot>(`/api/jobs/${currentJobId}/stream`)
      if (jobIdRef.current === currentJobId) {
        setSnapshot(next)
        setError(null)
      }
    } catch {
      setError('Транскрипт задачи временно недоступен')
    }
  }, [enabled])

  useEffect(() => {
    if (!jobId || !enabled) {
      setSnapshot(null)
      setError(null)
      return undefined
    }
    void pull()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void pull()
    }, pollMs)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void pull()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [jobId, enabled, pull, pollMs])

  return { snapshot, error, refresh: pull }
}
