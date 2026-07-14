interface TelegramHapticFeedback {
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void
  notificationOccurred(type: 'error' | 'success' | 'warning'): void
  selectionChanged(): void
}

interface TelegramWebApp {
  initData: string
  colorScheme?: 'light' | 'dark'
  isExpanded?: boolean
  safeAreaInset?: { top: number; bottom: number; left: number; right: number }
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number }
  ready(): void
  expand(): void
  onEvent?: (eventType: string, callback: () => void) => void
  offEvent?: (eventType: string, callback: () => void) => void
  requestFullscreen?: () => void
  setHeaderColor?: (color: string) => void
  setBackgroundColor?: (color: string) => void
  setBottomBarColor?: (color: string) => void
  HapticFeedback?: TelegramHapticFeedback
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export const telegram = () => window.Telegram?.WebApp

const DARK_CANVAS = '#050c0b'

/**
 * `telegram-web-app.js` injects a `window.Telegram.WebApp` stub even in a plain
 * browser tab, complete with a no-op `ready()`/`expand()`. The only reliable signal
 * that we are actually running inside a Telegram WebView is a non-empty `initData`,
 * so detection must key off that rather than the object's mere presence.
 */
export function isTelegramWebApp(): boolean {
  return Boolean(getTelegramInitData())
}

/** Force BeachOps dark chrome inside Telegram regardless of client colorScheme. */
export function applyBeachOpsDarkTheme(): void {
  document.documentElement.dataset.theme = 'dark'
  document.documentElement.style.colorScheme = 'dark'
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', DARK_CANVAS)

  const app = telegram()
  try {
    app?.setHeaderColor?.(DARK_CANVAS)
    app?.setBackgroundColor?.(DARK_CANVAS)
    app?.setBottomBarColor?.(DARK_CANVAS)
  } catch {
    // Optional Telegram theme APIs.
  }
}

let lastSafeAreaKey = ''

function applySafeAreaInsets(): void {
  const app = telegram()
  const root = document.documentElement
  const inset = app?.safeAreaInset ?? app?.contentSafeAreaInset
  if (!inset) return

  const key = `${inset.top}|${inset.bottom}|${inset.left}|${inset.right}`
  if (key === lastSafeAreaKey) return
  lastSafeAreaKey = key

  root.style.setProperty('--tg-safe-area-inset-top', `${inset.top}px`)
  root.style.setProperty('--tg-safe-area-inset-bottom', `${inset.bottom}px`)
  root.style.setProperty('--tg-safe-area-inset-left', `${inset.left}px`)
  root.style.setProperty('--tg-safe-area-inset-right', `${inset.right}px`)
}

let safeAreaListener: (() => void) | null = null

export function initializeTelegram(): void {
  const app = telegram()
  app?.ready()
  app?.expand()
  applyBeachOpsDarkTheme()
  applySafeAreaInsets()

  if (app?.onEvent && !safeAreaListener) {
    safeAreaListener = () => applySafeAreaInsets()
    app.onEvent('viewportChanged', safeAreaListener)
    app.onEvent('safeAreaChanged', safeAreaListener)
  }
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

/** Product is dark-only; kept for callers that still ask. */
export function telegramTheme(): 'dark' {
  return 'dark'
}
