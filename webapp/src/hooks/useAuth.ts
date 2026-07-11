import { useCallback, useEffect, useState } from 'react'
import {
  currentUser,
  loginWithTelegramWidget,
  logoutBrowserSession,
  mintSessionFromTelegram,
  type AuthenticatedUser,
  type TelegramLoginUser,
} from '../lib/auth'
import { ApiError } from '../lib/api'
import {
  getTelegramInitData,
  isTelegramWebApp,
  waitForTelegramInitData,
} from '../lib/telegram'
import { feedback } from '../lib/feedback'

function authErrorMessage(err: unknown, insideTelegram: boolean): string | null {
  if (!insideTelegram) return null
  if (err instanceof ApiError) {
    const detail = err.message.toLowerCase()
    if (
      err.status === 403
      || detail.includes('allowlist')
      || detail.includes('not allowlisted')
    ) {
      return 'Нет доступа для этого Telegram-аккаунта.'
    }
    if (err.status >= 500) {
      return 'Сервер временно недоступен. Нажмите «Повторить вход».'
    }
    if (err.status === 401) {
      return 'Не удалось подтвердить Telegram-сессию. Откройте Mini App заново из бота (/dashboard).'
    }
    return 'Не удалось войти. Нажмите «Повторить вход».'
  }
  return 'Нет связи с сервером. Проверьте сеть и нажмите «Повторить вход».'
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
      const inTg = isTelegramWebApp()
      setInsideTelegram(inTg)
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
    } catch (err) {
      setUser(null)
      setError(authErrorMessage(err, isTelegramWebApp()))
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
