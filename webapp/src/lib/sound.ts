/**
 * Tiny synthesized UI sound layer. Deliberately not sample-based: a handful of
 * short, quiet sine/triangle tones through a gentle lowpass keep the palette
 * consistent, avoid shipping audio assets, and stay "premium-soft" rather
 * than a chirpy notification-sound-effects-pack feel.
 */

const STORAGE_KEY = 'beachops:sound-muted'

export type SoundKind = 'tap' | 'success' | 'warning' | 'error'

interface Tone {
  freq: number
  at: number
  duration: number
  gain: number
  type?: OscillatorType
}

const RECIPES: Record<SoundKind, Tone[]> = {
  tap: [{ freq: 880, at: 0, duration: 0.05, gain: 0.05, type: 'triangle' }],
  success: [
    { freq: 660, at: 0, duration: 0.09, gain: 0.05, type: 'sine' },
    { freq: 988, at: 0.06, duration: 0.16, gain: 0.055, type: 'sine' },
  ],
  warning: [{ freq: 520, at: 0, duration: 0.13, gain: 0.05, type: 'sine' }],
  error: [
    { freq: 415, at: 0, duration: 0.1, gain: 0.05, type: 'sine' },
    { freq: 311, at: 0.08, duration: 0.18, gain: 0.045, type: 'sine' },
  ],
}

let audioCtx: AudioContext | null = null
let muted = readMuted()

function readMuted(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function getContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext
    ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  if (!audioCtx) audioCtx = new Ctor()
  if (audioCtx.state === 'suspended') void audioCtx.resume()
  return audioCtx
}

export function isSoundMuted(): boolean {
  return muted
}

export function setSoundMuted(next: boolean): void {
  muted = next
  try {
    localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
  } catch {
    // Best-effort persistence only — muting still works for this session.
  }
}

export function playSound(kind: SoundKind): void {
  if (muted) return
  const ctx = getContext()
  if (!ctx) return

  const master = ctx.createGain()
  master.gain.value = 1
  master.connect(ctx.destination)
  const softener = ctx.createBiquadFilter()
  softener.type = 'lowpass'
  softener.frequency.value = 2600
  softener.connect(master)

  for (const tone of RECIPES[kind]) {
    const osc = ctx.createOscillator()
    osc.type = tone.type ?? 'sine'
    osc.frequency.value = tone.freq
    const gain = ctx.createGain()
    const startAt = ctx.currentTime + tone.at
    const endAt = startAt + tone.duration
    gain.gain.setValueAtTime(0.0001, startAt)
    gain.gain.linearRampToValueAtTime(tone.gain, startAt + 0.012)
    gain.gain.exponentialRampToValueAtTime(0.0001, endAt)
    osc.connect(gain)
    gain.connect(softener)
    osc.start(startAt)
    osc.stop(endAt + 0.02)
  }
}
