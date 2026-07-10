import { getTelegramInitData } from './telegram'

export class ApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? ''

export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return configuredBaseUrl ? new URL(normalizedPath, configuredBaseUrl).toString() : normalizedPath
}

export function voiceWebSocketUrl(): string {
  const httpUrl = new URL(apiUrl('/api/voice/ws'), window.location.href)
  httpUrl.protocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  return httpUrl.toString()
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const initData = getTelegramInitData()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (initData) {
    headers.set('Authorization', `tma ${initData}`)
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: 'same-origin',
  })
  if (!response.ok) {
    let message = response.status === 401 ? 'Authentication required' : 'Request failed'
    try {
      const payload = await response.json() as { detail?: unknown }
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        message = payload.detail
      }
    } catch {
      // keep default message
    }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
