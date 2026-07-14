import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { readVoiceMode, writeVoiceMode } from './voiceMode'

describe('voiceMode', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('defaults to ask', () => {
    expect(readVoiceMode()).toBe('ask')
  })

  it('persists selected mode', () => {
    writeVoiceMode('plan')
    expect(readVoiceMode()).toBe('plan')
    writeVoiceMode('do')
    expect(readVoiceMode()).toBe('do')
  })

  it('ignores invalid stored values', () => {
    localStorage.setItem('beachops:voice-mode', 'nope')
    expect(readVoiceMode()).toBe('ask')
  })
})
