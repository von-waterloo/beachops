import { MessageCircle, RefreshCw, ShieldCheck } from 'lucide-react'
import { feedback } from '../lib/feedback'

interface AuthScreenProps {
  checking: boolean
  busy: boolean
  error: string | null
  supported: boolean
  insideTelegram: boolean
  onLogin: () => void
  onRetry: () => void
}

export function AuthScreen({
  checking,
  busy,
  error,
  insideTelegram,
  onRetry,
}: AuthScreenProps) {
  const waiting = checking || busy
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
                : 'Откройте BeachOps в Telegram'}
          </h1>
          <p>
            {insideTelegram
              ? 'Вход идёт по вашей Telegram-сессии — ничего настраивать не нужно.'
              : 'Самый простой и безопасный способ: бот → команда /dashboard. Passkey больше не нужен.'}
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
          <p className="auth-error" style={{ color: 'var(--muted)' }}>
            В Telegram напишите боту команду <strong>/dashboard</strong> и откройте Mini App оттуда.
          </p>
        )}

        {error && <p className="auth-error">{error}</p>}

        <div className="auth-trust">
          <span><i /> Telegram initData</span>
          <span><i /> Без паролей</span>
          <span><i /> Только allowlist</span>
        </div>
      </section>
    </main>
  )
}
