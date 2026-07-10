import { useCallback, useEffect, useState } from 'react'
import {
  currentUser,
  loginWithPasskey,
  logoutBrowserSession,
  passkeysSupported,
  registerPasskey,
  type AuthenticatedUser,
} from '../lib/passkeys'
import {
  getTelegramInitData,
  isTelegramWebApp,
  waitForTelegramInitData,
} from '../lib/telegram'
import { feedback } from '../lib/feedback'
import { ApiError } from '../lib/api'

function passkeyErrorMessage(cause: unknown, registering: boolean): string {
  if (cause instanceof DOMException) {
    if (cause.name === 'NotAllowedError') {
      return registering
        ? 'Создание ключа отменено или недоступно в этом WebView.'
        : 'Вход отменён или ключ на этом устройстве не найден.'
    }
    if (cause.name === 'NotSupportedError' || cause.name === 'InvalidStateError') {
      return 'Passkey недоступен в Telegram WebView. Откройте beachops.marketolog.tech в Chrome/Safari.'
    }
  }
  if (cause instanceof ApiError) {
    return cause.message
  }
  if (isTelegramWebApp()) {
    return registering
      ? 'В Telegram Android/iOS WebView Passkey часто не работает. Откройте сайт в браузере и привяжите ключ там, либо продолжайте вход через Telegram.'
      : 'Ключ не найден. Привяжите Passkey в браузере (не в WebView Telegram), затем войдите.'
  }
  return registering
    ? 'Не удалось создать ключ доступа'
    : 'Ключ не найден. Откройте Mini App в Telegram и привяжите Passkey, затем повторите вход.'
}

export function useAuth() {
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [checking, setChecking] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [insideTelegram, setInsideTelegram] = useState(() => isTelegramWebApp())

  const refresh = useCallback(async () => {
    setChecking(true)
    try {
      if (!getTelegramInitData()) {
        await waitForTelegramInitData()
      }
      setInsideTelegram(isTelegramWebApp())
      setUser(await currentUser())
      setError(null)
    } catch {
      setUser(null)
      // Inside Telegram, a failed /api/me after a real initData means the
      // account is not whitelisted. Outside Telegram it just means "not signed
      // in yet" — the passkey login button handles that, no error needed.
      setError(isTelegramWebApp() ? 'Нет доступа для этого Telegram-аккаунта.' : null)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      await loginWithPasskey()
      await refresh()
      feedback('success')
    } catch (cause) {
      setError(passkeyErrorMessage(cause, false))
      feedback('error')
    } finally {
      setBusy(false)
    }
  }, [refresh])

  const register = useCallback(async () => {
    setBusy(true)
    setError(null)
    if (!passkeysSupported()) {
      setError('Passkey не поддерживается в этом окружении. Откройте сайт в Chrome/Safari.')
      feedback('error')
      setBusy(false)
      return
    }
    try {
      // Telegram Android WebView often reports PublicKeyCredential but cannot complete UVPA.
      if (typeof PublicKeyCredential !== 'undefined'
        && 'isUserVerifyingPlatformAuthenticatorAvailable' in PublicKeyCredential) {
        const available = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
        if (!available && isTelegramWebApp()) {
          setError(
            'Отпечаток/Face ID в Telegram WebView недоступен. Откройте https://beachops.marketolog.tech в Chrome, войдите через Telegram один раз… или просто продолжайте в Mini App без Passkey.',
          )
          feedback('warning')
          setBusy(false)
          return
        }
      }
      await registerPasskey()
      await refresh()
      feedback('success')
    } catch (cause) {
      setError(passkeyErrorMessage(cause, true))
      feedback('error')
    } finally {
      setBusy(false)
    }
  }, [refresh])

  const logout = useCallback(async () => {
    setBusy(true)
    try {
      await logoutBrowserSession()
      feedback('select')
    } finally {
      setUser(null)
      setBusy(false)
    }
  }, [])

  return {
    user,
    checking,
    busy,
    error,
    supported: passkeysSupported(),
    insideTelegram,
    login,
    register,
    logout,
    refresh,
  }
}
