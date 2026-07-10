import { describe, expect, it } from 'vitest'
import {
  isFatalVoiceErrorCode,
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

  it('stops when a fatal server error was already observed', () => {
    expect(
      shouldReconnectVoice({
        intentionallyClosed: false,
        online: true,
        closeCode: 1006,
        attempts: 0,
        fatalFailure: true,
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

describe('isFatalVoiceErrorCode', () => {
  it('recognizes auth and rate-limit payloads', () => {
    expect(isFatalVoiceErrorCode('unauthorized')).toBe(true)
    expect(isFatalVoiceErrorCode('rate_limited')).toBe(true)
    expect(isFatalVoiceErrorCode('provider_unavailable')).toBe(false)
  })
})

describe('voiceReconnectDelayMs', () => {
  it('uses exponential backoff capped at 12s', () => {
    expect(voiceReconnectDelayMs(0, 0)).toBe(600)
    expect(voiceReconnectDelayMs(1, 0)).toBe(1200)
    expect(voiceReconnectDelayMs(5, 0)).toBe(12_000)
    expect(voiceReconnectDelayMs(10, 0)).toBe(12_000)
  })
})
