import { useEffect, useRef, useState } from 'react'
import { MessageCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  fetchTelegramLoginConfig,
  type TelegramLoginUser,
} from '../lib/auth'
import { feedback } from '../lib/feedback'

const WIDGET_CALLBACK = 'onBeachOpsTelegramAuth'

declare global {
  interface Window {
    onBeachOpsTelegramAuth?: (user: TelegramLoginUser) => void
  }
}

interface AuthScreenProps {
  checking: boolean
  busy: boolean
  error: string | null
  insideTelegram: boolean
  onTelegramLogin: (user: TelegramLoginUser) => void
  onRetry: () => void
}

export function AuthScreen({
  checking,
  busy,
  error,
  insideTelegram,
  onTelegramLogin,
  onRetry,
}: AuthScreenProps) {
  const waiting = checking || busy
  const widgetHostRef = useRef<HTMLDivElement | null>(null)
  const [widgetError, setWidgetError] = useState<string | null>(null)
  const [botUsername, setBotUsername] = useState<string | null>(null)

  useEffect(() => {
    if (insideTelegram || checking) return

    let cancelled = false
    const host = widgetHostRef.current

    window[WIDGET_CALLBACK] = (user: TelegramLoginUser) => {
      feedback('tap')
      onTelegramLogin(user)
    }

    void (async () => {
      try {
        const config = await fetchTelegramLoginConfig()
        if (cancelled) return
        if (!config.loginEnabled || !config.botUsername) {
          setWidgetError(
            'Вход с сайта временно недоступен. Откройте бота → /dashboard.',
          )
          return
        }
        setBotUsername(config.botUsername)
        if (!host) return
        host.replaceChildren()
        const script = document.createElement('script')
        script.async = true
        script.src = 'https://telegram.org/js/telegram-widget.js?22'
        script.setAttribute('data-telegram-login', config.botUsername)
        script.setAttribute('data-size', 'large')
        script.setAttribute('data-radius', '12')
        script.setAttribute('data-request-access', 'write')
        script.setAttribute('data-onauth', `${WIDGET_CALLBACK}(user)`)
        script.setAttribute('data-userpic', 'false')
        host.appendChild(script)
      } catch {
        if (!cancelled) {
          setWidgetError(
            'Не удалось загрузить вход Telegram. Откройте бота → /dashboard.',
          )
        }
      }
    })()

    return () => {
      cancelled = true
      delete window[WIDGET_CALLBACK]
      host?.replaceChildren()
    }
  }, [checking, insideTelegram, onTelegramLogin])

  return (
    <main className="auth-screen">
      <section className="auth-card" aria-live="polite">
        <div className={`biometric-orbit ${waiting ? 'scanning' : ''}`} aria-hidden="true">
          <span className="orbit orbit-one" />
          <span className="orbit orbit-two" />
          <span className="biometric-core">
            <MessageCircle size={44} />
          </span>
        </div>

        <div className="auth-copy">
          <span className="auth-kicker">
            <ShieldCheck size={15} />
            Вход через Telegram
          </span>
          <h1>
            {checking
              ? 'Проверяем доступ'
              : insideTelegram
                ? 'Подключаем Mini App'
                : 'Войдите через Telegram'}
          </h1>
          <p>
            {insideTelegram
              ? 'Вход идёт по вашей Telegram-сессии — ничего настраивать не нужно.'
              : 'Один аккаунт для Mini App и сайта. Нажмите кнопку ниже и подтвердите в Telegram.'}
          </p>
        </div>

        {!checking && insideTelegram && (
          <button
            className="passkey-button"
            type="button"
            disabled={busy}
            onClick={() => {
              feedback('tap')
              onRetry()
            }}
          >
            <RefreshCw size={19} />
            {busy ? 'Подключаем…' : 'Повторить вход'}
          </button>
        )}

        {!checking && !insideTelegram && (
          <div className="telegram-login-slot">
            <div ref={widgetHostRef} className="telegram-login-widget" />
            {botUsername && (
              <p className="muted-hint" style={{ marginTop: '0.75rem' }}>
                Или в боте @{botUsername}: команда /dashboard
              </p>
            )}
            {widgetError && <p className="auth-error">{widgetError}</p>}
          </div>
        )}

        {error && <p className="auth-error">{error}</p>}

        <div className="auth-trust">
          <span><i /> Telegram Login</span>
          <span><i /> Без паролей</span>
          <span><i /> Только allowlist</span>
        </div>
      </section>
    </main>
  )
}
