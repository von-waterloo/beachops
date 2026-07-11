import { useCallback, useEffect, useState } from 'react'
import {
  currentUser,
  loginWithTelegramWidget,
  logoutBrowserSession,
  mintSessionFromTelegram,
  type AuthenticatedUser,
  type TelegramLoginUser,
} from '../lib/auth'
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
      const next = await currentUser()
      setUser(next)
      setError(null)
      // Best-effort: Mini App also gets the shared session cookie for WS/API.
      if (getTelegramInitData()) {
        try {
          await mintSessionFromTelegram()
        } catch {
          // Cookie mint is optional when initData Authorization already works.
        }
      }
    } catch {
      setUser(null)
      setError(
        isTelegramWebApp()
          ? 'Нет доступа для этого Telegram-аккаунта.'
          : null,
      )
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const loginWithTelegram = useCallback(async (payload: TelegramLoginUser) => {
    setBusy(true)
    setError(null)
    try {
      await loginWithTelegramWidget(payload)
      await refresh()
      feedback('success')
    } catch {
      setError('Вход через Telegram не удался. Проверьте, что аккаунт в allowlist.')
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
    insideTelegram,
    loginWithTelegram,
    logout,
    refresh,
  }
}
