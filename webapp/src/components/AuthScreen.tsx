import { Fingerprint, KeyRound, RefreshCw, ScanFace, ShieldCheck } from 'lucide-react'
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
  supported,
  insideTelegram,
  onLogin,
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
            {waiting ? <ScanFace size={44} /> : <Fingerprint size={48} />}
          </span>
        </div>

        <div className="auth-copy">
          <span className="auth-kicker">
            <ShieldCheck size={15} />
            PRIVATE CONTROL PLANE
          </span>
          <h1>
            {checking
              ? 'Проверяем доступ'
              : insideTelegram
                ? 'Вход через Telegram'
                : 'Вход в BeachOps'}
          </h1>
          <p>
            {insideTelegram
              ? 'В Mini App вход идёт по вашей Telegram-сессии. Отпечаток можно привязать после входа — для браузера вне Telegram.'
              : 'Сначала привяжите ключ в Telegram Mini App (кнопка с отпечатком после /dashboard). Затем здесь — Face ID, Windows Hello или PIN. QR с телефона сработает только если ключ в облачном менеджере паролей, а не только в Windows Hello.'}
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
          <button
            className="passkey-button"
            type="button"
            disabled={busy || !supported}
            onClick={() => {
              feedback('tap')
              onLogin()
            }}
          >
            <KeyRound size={19} />
            {busy ? 'Подтвердите на устройстве…' : 'Войти с ключом доступа'}
          </button>
        )}

        {!checking && !insideTelegram && !supported && (
          <p className="auth-error">
            Этот браузер не поддерживает ключи доступа. Откройте BeachOps через /dashboard в Telegram.
          </p>
        )}
        {error && <p className="auth-error">{error}</p>}

        <div className="auth-trust">
          <span><i /> {insideTelegram ? 'Telegram session' : 'WebAuthn'}</span>
          <span><i /> End-to-end challenge</span>
          <span><i /> Owner only</span>
        </div>
      </section>
    </main>
  )
}
