import { Fingerprint, KeyRound, ScanFace, ShieldCheck } from 'lucide-react'

interface AuthScreenProps {
  checking: boolean
  busy: boolean
  error: string | null
  supported: boolean
  onLogin: () => void
}

export function AuthScreen({
  checking,
  busy,
  error,
  supported,
  onLogin,
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
          <h1>{checking ? 'Проверяем доступ' : 'Вход в BeachOps'}</h1>
          <p>
            Face ID, отпечаток, Windows Hello или системный PIN.
            Пароль не передаётся и не хранится на сервере.
          </p>
        </div>

        {!checking && (
          <button
            className="passkey-button"
            type="button"
            disabled={busy || !supported}
            onClick={onLogin}
          >
            <KeyRound size={19} />
            {busy ? 'Подтвердите на устройстве…' : 'Войти с ключом доступа'}
          </button>
        )}

        {!supported && (
          <p className="auth-error">Этот браузер не поддерживает ключи доступа.</p>
        )}
        {error && <p className="auth-error">{error}</p>}

        <div className="auth-trust">
          <span><i /> WebAuthn</span>
          <span><i /> End-to-end challenge</span>
          <span><i /> Owner only</span>
        </div>
      </section>
    </main>
  )
}
