import { afterEach, describe, expect, it } from 'vitest'
import { isSoundMuted, playSound, setSoundMuted } from './sound'

describe('sound mute preference', () => {
  afterEach(() => {
    setSoundMuted(false)
  })

  it('persists the mute flag across calls', () => {
    expect(isSoundMuted()).toBe(false)
    setSoundMuted(true)
    expect(isSoundMuted()).toBe(true)
    expect(localStorage.getItem('beachops:sound-muted')).toBe('1')
  })

  it('never throws, even without a Web Audio API in the environment', () => {
    expect(() => playSound('tap')).not.toThrow()
    setSoundMuted(true)
    expect(() => playSound('error')).not.toThrow()
  })
})
