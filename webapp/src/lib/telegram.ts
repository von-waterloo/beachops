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

export function initializeTelegram(): void {
  const app = telegram()
  app?.ready()
  app?.expand()
}

export function getTelegramInitData(): string {
  return telegram()?.initData ?? ''
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
