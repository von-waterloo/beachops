import { apiFetch } from './api'

export interface CursorModelOption {
  key: string
  label: string
}

export type AuthMethod = 'telegram' | 'telegram_login' | 'session' | 'passkey'

export interface AuthenticatedUser {
  userId: number
  role: string
  writesEnabled: boolean
  authMethod: AuthMethod
  hasPasskey: boolean
  cursorModelKey?: string
  models?: CursorModelOption[]
}

export interface TelegramLoginConfig {
  botUsername: string | null
  botId?: number | null
  loginEnabled: boolean
  origin: string | null
  expectedHost?: string | null
}

/** Payload returned by Telegram Login Widget `data-onauth`. */
export interface TelegramLoginUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

const TG_AUTH_RESULT_RE = /[#?&]tgAuthResult=([A-Za-z0-9\-_=]+)/

function decodeTgAuthResultPayload(encoded: string): TelegramLoginUser | null {
  try {
    let data = encoded.replace(/-/g, '+').replace(/_/g, '/')
    const pad = data.length % 4
    if (pad > 1) {
      data += '='.repeat(4 - pad)
    }
    const parsed = JSON.parse(atob(data)) as Record<string, unknown>
    const id = Number(parsed.id)
    const authDate = Number(parsed.auth_date)
    const hash = String(parsed.hash || '')
    const firstName = String(parsed.first_name || '')
    if (!Number.isFinite(id) || !Number.isFinite(authDate) || hash.length !== 64 || !firstName) {
      return null
    }
    const user: TelegramLoginUser = {
      id,
      first_name: firstName,
      auth_date: authDate,
      hash,
    }
    if (typeof parsed.last_name === 'string' && parsed.last_name) {
      user.last_name = parsed.last_name
    }
    if (typeof parsed.username === 'string' && parsed.username) {
      user.username = parsed.username
    }
    if (typeof parsed.photo_url === 'string' && parsed.photo_url) {
      user.photo_url = parsed.photo_url
    }
    return user
  } catch {
    return null
  }
}

/** Read Telegram OAuth / Login Widget return payload from the URL hash or query. */
export function consumeTelegramAuthResult(
  href: string = typeof window !== 'undefined' ? window.location.href : '',
): TelegramLoginUser | null {
  const match = href.match(TG_AUTH_RESULT_RE)
  if (!match?.[1]) return null
  const user = decodeTgAuthResultPayload(match[1])
  if (!user) return null
  if (typeof window !== 'undefined') {
    const url = new URL(href, window.location.origin)
    if (url.hash.includes('tgAuthResult=')) {
      url.hash = ''
    }
    if (url.searchParams.has('tgAuthResult')) {
      url.searchParams.delete('tgAuthResult')
    }
    window.history.replaceState(
      {},
      '',
      `${url.pathname}${url.search}${url.hash}`,
    )
  }
  return user
}

/** Same-window OAuth URL (Telegram redirects back with `#tgAuthResult=`). */
export function telegramOauthUrl(config: TelegramLoginConfig): string | null {
  if (!config.botId || !config.origin) return null
  const params = new URLSearchParams({
    bot_id: String(config.botId),
    origin: config.origin,
    request_access: 'write',
    return_to: typeof window !== 'undefined' ? window.location.href.split('#')[0] : config.origin,
  })
  return `https://oauth.telegram.org/auth?${params.toString()}`
}

export async function currentUser(): Promise<AuthenticatedUser> {
  return apiFetch<AuthenticatedUser>('/api/me')
}

export async function setCursorModel(modelKey: string): Promise<{
  cursorModelKey: string
  label: string
}> {
  return apiFetch('/api/me/model', {
    method: 'PUT',
    body: JSON.stringify({ modelKey }),
  })
}

export async function fetchTelegramLoginConfig(): Promise<TelegramLoginConfig> {
  return apiFetch<TelegramLoginConfig>('/api/auth/telegram/config')
}

export async function loginWithTelegramWidget(
  user: TelegramLoginUser,
): Promise<void> {
  await apiFetch('/api/auth/telegram/login', {
    method: 'POST',
    body: JSON.stringify(user),
  })
}

/** After Mini App initData auth, mint the shared browser session cookie. */
export async function mintSessionFromTelegram(): Promise<void> {
  await apiFetch('/api/auth/session', { method: 'POST' })
}

export async function logoutBrowserSession(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' })
}
