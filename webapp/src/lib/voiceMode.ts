import type { VoiceAgentMode } from '../voice/state'

const STORAGE_KEY = 'beachops:voice-mode'

export function readVoiceMode(): VoiceAgentMode {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'ask' || value === 'plan' || value === 'do') return value
  } catch {
    // ignore private mode / quota errors
  }
  return 'ask'
}

export function writeVoiceMode(mode: VoiceAgentMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // ignore
  }
}
