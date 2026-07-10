import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'
import { apiFetch } from './api'

interface PasskeyOptions<T> {
  challengeId: string
  options: T
}

export interface AuthenticatedUser {
  userId: number
  role: string
  writesEnabled: boolean
  authMethod: 'telegram' | 'passkey'
  hasPasskey: boolean
}

export async function currentUser(): Promise<AuthenticatedUser> {
  return apiFetch<AuthenticatedUser>('/api/me')
}

export async function registerPasskey(label?: string): Promise<void> {
  const ceremony = await apiFetch<PasskeyOptions<PublicKeyCredentialCreationOptionsJSON>>(
    '/api/auth/passkeys/register/options',
    { method: 'POST' },
  )
  const credential = await startRegistration({ optionsJSON: ceremony.options })
  await apiFetch('/api/auth/passkeys/register/verify', {
    method: 'POST',
    body: JSON.stringify({
      challengeId: ceremony.challengeId,
      credential,
      label: label || deviceLabel(),
    }),
  })
}

export async function loginWithPasskey(): Promise<void> {
  const ceremony = await apiFetch<PasskeyOptions<PublicKeyCredentialRequestOptionsJSON>>(
    '/api/auth/passkeys/login/options',
    { method: 'POST' },
  )
  const credential = await startAuthentication({ optionsJSON: ceremony.options })
  await apiFetch('/api/auth/passkeys/login/verify', {
    method: 'POST',
    body: JSON.stringify({
      challengeId: ceremony.challengeId,
      credential,
    }),
  })
}

export async function logoutBrowserSession(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' })
}

export function passkeysSupported(): boolean {
  return Boolean(
    typeof window !== 'undefined'
    && window.PublicKeyCredential
    && typeof window.PublicKeyCredential === 'function'
    && navigator.credentials
    && typeof navigator.credentials.create === 'function'
    && typeof navigator.credentials.get === 'function'
    && window.isSecureContext,
  )
}

function deviceLabel(): string {
  const platform = navigator.platform || 'Device'
  return `${platform} passkey`.slice(0, 80)
}
