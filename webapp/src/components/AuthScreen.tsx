import { useEffect, useRef, useState } from 'react'
import { ExternalLink, MessageCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  consumeTelegramAuthResult,
  fetchTelegramLoginConfig,
  telegramOauthUrl,
  type TelegramLoginUser,
} from '../lib/auth'
import { feedback } from '../lib/feedback'

const WIDGET_CALLBACK = 'onBeachOpsTelegramAuth'
const WIDGET_WAIT_MS = 3200

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
    `Встроенная кнопка Telegram не отобразилась. В BotFather: /setdomain = ${domain} `
    + '(без www и без https://). Можно войти кнопкой ниже.'
  )
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
  const consumedReturnRef = useRef(false)
  const [widgetError, setWidgetError] = useState<string | null>(null)
  const [botUsername, setBotUsername] = useState<string | null>(null)
  const [oauthUrl, setOauthUrl] = useState<string | null>(null)
  const [configReady, setConfigReady] = useState(false)

  // OAuth return: Telegram redirects back with #tgAuthResult=… — handle before widget.
  useEffect(() => {
    if (insideTelegram || consumedReturnRef.current) return
    const user = consumeTelegramAuthResult()
    if (!user) return
    consumedReturnRef.current = true
    feedback('tap')
    onLoginRef.current(user)
  }, [insideTelegram])

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
        if (!config.loginEnabled || !config.botUsername || !config.botId) {
          setWidgetError(
            'Вход с сайта временно недоступен. Откройте бота → /dashboard.',
          )
          setConfigReady(true)
          return
        }
        setBotUsername(config.botUsername)
        setOauthUrl(telegramOauthUrl(config))
        setConfigReady(true)

        await new Promise<void>((resolve) => {
          window.requestAnimationFrame(() => resolve())
        })
        if (cancelled) return
        const host = widgetHostRef.current
        if (!host) {
          setWidgetError(setDomainHint(config.expectedHost))
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
          }
        }, WIDGET_WAIT_MS)
      } catch {
        if (!cancelled) {
          setWidgetError(
            'Не удалось загрузить вход Telegram. Откройте бота → /dashboard или обновите страницу.',
          )
          setConfigReady(true)
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
            {configReady && oauthUrl && (
              <a
                className="passkey-button telegram-oauth-fallback"
                href={oauthUrl}
                onClick={() => feedback('tap')}
              >
                <ExternalLink size={19} />
                {busy ? 'Входим…' : 'Открыть вход Telegram'}
              </a>
            )}
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
