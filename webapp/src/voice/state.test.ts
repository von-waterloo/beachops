import { describe, expect, it } from 'vitest'
import { initialVoiceState, voiceReducer } from './state'

describe('voiceReducer', () => {
  it('moves through capture, transcript confirmation, and planning', () => {
    const listening = voiceReducer(initialVoiceState, { type: 'START_LISTENING', at: 100 })
    expect(listening.phase).toBe('listening')
    expect(listening.recordingStartedAt).toBe(100)

    const transcribing = voiceReducer(listening, { type: 'STOP_LISTENING' })
    expect(transcribing.phase).toBe('transcribing')

    const partial = voiceReducer(transcribing, { type: 'PARTIAL', text: 'Deploy the' })
    expect(partial.partialTranscript).toBe('Deploy the')

    const confirming = voiceReducer(partial, { type: 'FINAL', text: 'Deploy the service' })
    expect(confirming.phase).toBe('confirming')
    expect(confirming.transcript).toBe('Deploy the service')

    const planning = voiceReducer(confirming, { type: 'CONFIRM' })
    expect(planning.phase).toBe('planning')
  })

  it('does not plan an empty transcript', () => {
    const confirming = { ...initialVoiceState, phase: 'confirming' as const }
    expect(voiceReducer(confirming, { type: 'CONFIRM' })).toEqual(confirming)
  })

  it('returns to idle after cancellation while preserving connection', () => {
    const listening = {
      ...initialVoiceState,
      connected: true,
      phase: 'listening' as const,
      recordingStartedAt: 100,
    }
    const cancelled = voiceReducer(listening, { type: 'CANCEL' })
    expect(cancelled.phase).toBe('idle')
    expect(cancelled.connected).toBe(true)
    expect(cancelled.recordingStartedAt).toBeNull()
  })

  it('submits typed composer text into planning', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Inspect the deploy pipeline',
    })
    expect(planning.phase).toBe('planning')
    expect(planning.transcript).toBe('Inspect the deploy pipeline')
  })

  it('updates caption from live job progress while planning', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Что в очереди?',
      mode: 'ask',
    })
    const live = voiceReducer(planning, {
      type: 'PROGRESS',
      caption: 'Смотрю активные задачи…',
    })
    expect(live.phase).toBe('planning')
    expect(live.caption).toBe('Смотрю активные задачи…')
  })

  it('keeps planning on plan.started and refreshes caption', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Статус воркеров',
      mode: 'ask',
    })
    const started = voiceReducer(planning, { type: 'PLAN_STARTED', mode: 'ask' })
    expect(started.phase).toBe('planning')
    expect(started.caption).toContain('control room')
  })

  it('supports barge-in by returning from speaking to listening', () => {
    const speaking = voiceReducer(initialVoiceState, { type: 'SPEAKING', caption: 'Working' })
    const listening = voiceReducer(speaking, { type: 'START_LISTENING', at: 200 })
    expect(listening.phase).toBe('listening')
    expect(listening.caption).toContain('Слушаю')
  })
})
