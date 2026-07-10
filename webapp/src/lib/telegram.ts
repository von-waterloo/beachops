interface TelegramHapticFeedback {
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void
  notificationOccurred(type: 'error' | 'success' | 'warning'): void
  selectionChanged(): void
}

interface TelegramWebApp {
  initData: string
  colorScheme?: 'light' | 'dark'
  isExpanded?: boolean
  ready(): void
  expand(): void
  requestFullscreen?: () => void
  HapticFeedback?: TelegramHapticFeedback
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export const telegram = () => window.Telegram?.WebApp

/**
 * `telegram-web-app.js` injects a `window.Telegram.WebApp` stub even in a plain
 * browser tab, complete with a no-op `ready()`/`expand()`. The only reliable signal
 * that we are actually running inside a Telegram WebView is a non-empty `initData`,
 * so detection must key off that rather than the object's mere presence.
 */
export function isTelegramWebApp(): boolean {
  return Boolean(getTelegramInitData())
}

export function initializeTelegram(): void {
  const app = telegram()
  app?.ready()
  app?.expand()
}

export function getTelegramInitData(): string {
  return telegram()?.initData ?? ''
}

/** Wait briefly for Telegram to inject initData into the WebView. */
export async function waitForTelegramInitData(
  timeoutMs = 2500,
): Promise<string> {
  const existing = getTelegramInitData()
  if (existing) return existing

  const started = Date.now()
  return new Promise((resolve) => {
    const tick = () => {
      initializeTelegram()
      const value = getTelegramInitData()
      if (value || Date.now() - started >= timeoutMs) {
        resolve(value)
        return
      }
      window.setTimeout(tick, 50)
    }
    tick()
  })
}

export function requestTelegramFullscreen(): void {
  try {
    telegram()?.requestFullscreen?.()
  } catch {
    // Fullscreen is an optional Telegram capability.
  }
}

export function haptic(
  kind: 'tap' | 'success' | 'warning' | 'error' | 'selection',
): void {
  const feedback = telegram()?.HapticFeedback
  if (!feedback) return
  if (kind === 'tap') feedback.impactOccurred('soft')
  else if (kind === 'selection') feedback.selectionChanged()
  else feedback.notificationOccurred(kind)
}

export function telegramTheme(): 'light' | 'dark' {
  return telegram()?.colorScheme ?? (
    window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  )
}
