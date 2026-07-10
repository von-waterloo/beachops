import { describe, expect, it } from 'vitest'
import {
  shouldReconnectVoice,
  voiceReconnectDelayMs,
  VOICE_RECONNECT_LIMIT,
} from './reconnect'

describe('shouldReconnectVoice', () => {
  it('reconnects for transient closes within the attempt budget', () => {
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 1006,
        attempts: 0,
      }),
    ).toBe(true)
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 1006,
        attempts: VOICE_RECONNECT_LIMIT - 1,
      }),
    ).toBe(true)
  })

  it('stops after the reconnect limit', () => {
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 1006,
        attempts: VOICE_RECONNECT_LIMIT,
      }),
    ).toBe(false)
  })

  it('never reconnects on auth or rate-limit closes', () => {
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 4401,
        attempts: 0,
      }),
    ).toBe(false)
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 4429,
        attempts: 0,
      }),
    ).toBe(false)
  })

  it('skips reconnect when closed on purpose or offline', () => {
    expect(
      shouldReconnectVoice({
        intentionallyClosed: true,
        online: true,
        closeCode: 1006,
        attempts: 0,
      }),
    ).toBe(false)
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: false,
        closeCode: 1006,
        attempts: 0,
      }),
    ).toBe(false)
  })
})

describe('voiceReconnectDelayMs', () => {
  it('uses exponential backoff capped at 8s', () => {
    expect(voiceReconnectDelayMs(0, 0)).toBe(500)
    expect(voiceReconnectDelayMs(1, 0)).toBe(1000)
    expect(voiceReconnectDelayMs(4, 0)).toBe(8000)
    expect(voiceReconnectDelayMs(10, 0)).toBe(8000)
  })
})
