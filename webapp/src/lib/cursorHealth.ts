import { apiFetch } from './api'

export interface CursorTokenHealth {
  tokenKey: string
  ok: boolean
  identity?: string | null
  error?: string | null
  repositoryCount?: number | null
  hasActiveRepo?: boolean | null
  active?: boolean
}

export interface CursorHealthSnapshot {
  ok: boolean
  activeTokenKey: string
  tokens: CursorTokenHealth[]
}

export async function fetchCursorHealth(refresh = false): Promise<CursorHealthSnapshot> {
  const suffix = refresh ? '?refresh=true' : ''
  return apiFetch<CursorHealthSnapshot>(`/api/cursor/health${suffix}`)
}
