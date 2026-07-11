import { useEffect, useRef, useState } from 'react'
import { ExternalLink, MessageCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  fetchTelegramLoginConfig,
  type TelegramLoginConfig,
  type TelegramLoginUser,
} from '../lib/auth'
import { feedback } from '../lib/feedback'

const WIDGET_CALLBACK = 'onBeachOpsTelegramAuth'
const WIDGET_WAIT_MS = 2800

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

function setDomainHint(host: string | null | undefined): string {
  const domain = host || 'beachops.marketolog.tech'
  return (
    `Виджет не загрузился. В BotFather: /setdomain = ${domain} `
    + '(без www и без https://). Обновите страницу на этом же host.'
  )
}

function oauthFallbackUrl(config: TelegramLoginConfig): string | null {
  if (!config.botId || !config.origin) return null
  const params = new URLSearchParams({
    bot_id: String(config.botId),
    origin: config.origin,
    embed: '1',
    request_access: 'write',
    return_to: window.location.href,
  })
  return `https://oauth.telegram.org/auth?${params.toString()}`
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
  const onLoginRef = useRef(onTelegramLogin)
  onLoginRef.current = onTelegramLogin
  const [widgetError, setWidgetError] = useState<string | null>(null)
  const [botUsername, setBotUsername] = useState<string | null>(null)
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(null)
  const [showFallback, setShowFallback] = useState(false)

  useEffect(() => {
    if (insideTelegram || checking) return

    let cancelled = false
    let waitTimer: number | undefined

    window[WIDGET_CALLBACK] = (user: TelegramLoginUser) => {
      feedback('tap')
      onLoginRef.current(user)
    }

    void (async () => {
      try {
        const config = await fetchTelegramLoginConfig()
        if (cancelled) return
        if (!config.loginEnabled || !config.botUsername) {
          setWidgetError(
            'Вход с сайта временно недоступен. Откройте бота → /dashboard.',
          )
          setShowFallback(true)
          return
        }
        setBotUsername(config.botUsername)
        setFallbackUrl(oauthFallbackUrl(config))

        // Wait one frame so the host div is mounted after checking flips false.
        await new Promise<void>((resolve) => {
          window.requestAnimationFrame(() => resolve())
        })
        if (cancelled) return
        const host = widgetHostRef.current
        if (!host) {
          setWidgetError(setDomainHint(config.expectedHost))
          setShowFallback(true)
          return
        }
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

        waitTimer = window.setTimeout(() => {
          if (cancelled) return
          const iframe = host.querySelector('iframe')
          if (!iframe || iframe.clientHeight < 8) {
            setWidgetError(setDomainHint(config.expectedHost))
            setShowFallback(true)
          }
        }, WIDGET_WAIT_MS)
      } catch {
        if (!cancelled) {
          setWidgetError(
            'Не удалось загрузить вход Telegram. Откройте бота → /dashboard.',
          )
          setShowFallback(true)
        }
      }
    })()

    return () => {
      cancelled = true
      window.clearTimeout(waitTimer)
      delete window[WIDGET_CALLBACK]
      widgetHostRef.current?.replaceChildren()
    }
  }, [checking, insideTelegram])

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
            {showFallback && fallbackUrl && (
              <a
                className="passkey-button telegram-oauth-fallback"
                href={fallbackUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => feedback('tap')}
              >
                <ExternalLink size={19} />
                Открыть вход Telegram
              </a>
            )}
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
