import { useCallback, useEffect, useState } from 'react'
import {
  currentUser,
  loginWithPasskey,
  logoutBrowserSession,
  passkeysSupported,
  registerPasskey,
  type AuthenticatedUser,
} from '../lib/passkeys'

export function useAuth() {
  const [user, setUser] = useState<AuthenticatedUser | null>(null)
  const [checking, setChecking] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setUser(await currentUser())
      setError(null)
    } catch {
      setUser(null)
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
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'NotAllowedError') {
        setError('Вход отменён')
      } else {
        setError('Ключ доступа не найден или вход не подтверждён')
      }
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
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'NotAllowedError') {
        setError('Создание ключа отменено')
      } else {
        setError('Не удалось создать ключ доступа')
      }
    } finally {
      setBusy(false)
    }
  }, [refresh])

  const logout = useCallback(async () => {
    setBusy(true)
    try {
      await logoutBrowserSession()
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
    login,
    register,
    logout,
  }
}
