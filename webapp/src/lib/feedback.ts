/**
 * Single entry point for "this interaction just happened" feedback: a
 * Telegram haptic pulse (only fires where `HapticFeedback` actually exists,
 * e.g. Android/iOS Telegram clients) plus a quiet synthesized tone. Kept as
 * one call site per action so we can stay deliberately sparing — see
 * `SOUND_MAP` for which kinds get a sound at all.
 */
import { haptic } from './telegram'
import { playSound, type SoundKind } from './sound'

export { isSoundMuted, setSoundMuted } from './sound'

export type FeedbackKind = 'tap' | 'select' | 'success' | 'warning' | 'error'

const HAPTIC_MAP: Record<FeedbackKind, 'tap' | 'success' | 'warning' | 'error' | 'selection'> = {
  tap: 'tap',
  select: 'selection',
  success: 'success',
  warning: 'warning',
  error: 'error',
}

// Navigation/selection stays haptic-only — sounding on every tab switch is
// exactly the kind of "борщ" we want to avoid.
const SOUND_MAP: Partial<Record<FeedbackKind, SoundKind>> = {
  tap: 'tap',
  success: 'success',
  warning: 'warning',
  error: 'error',
}

export function feedback(kind: FeedbackKind): void {
  haptic(HAPTIC_MAP[kind])
  const sound = SOUND_MAP[kind]
  if (sound) playSound(sound)
}
