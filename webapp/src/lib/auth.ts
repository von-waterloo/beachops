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
  loginEnabled: boolean
  origin: string | null
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
