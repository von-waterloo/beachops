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
      if (cause instanceof DOMException && cause.name === 'NotAllowedError') {
        setError('Вход отменён или ключ на этом устройстве не найден. Привяжите passkey в Telegram Mini App.')
      } else {
        setError('Ключ не найден. Откройте /dashboard в Telegram и нажмите кнопку с отпечатком, затем повторите вход.')
      }
      feedback('error')
    } finally {
      setBusy(false)
    }
  }, [refresh])

  const register = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      await registerPasskey()
      await refresh()
      feedback('success')
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'NotAllowedError') {
        setError('Создание ключа отменено')
      } else {
        setError('Не удалось создать ключ доступа')
      }
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
