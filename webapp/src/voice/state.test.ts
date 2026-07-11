import { describe, expect, it } from 'vitest'
import { initialVoiceState, voiceReducer } from './state'

describe('voiceReducer', () => {
  it('moves through capture, transcript confirmation, and planning', () => {
    const connected = voiceReducer(initialVoiceState, {
      type: 'CONNECTED',
      connected: true,
      voiceRequireConfirm: true,
    })
    const listening = voiceReducer(connected, { type: 'START_LISTENING', at: 100 })
    expect(listening.phase).toBe('listening')
    expect(listening.recordingStartedAt).toBe(100)

    const transcribing = voiceReducer(listening, { type: 'STOP_LISTENING' })
    expect(transcribing.phase).toBe('transcribing')

    const partial = voiceReducer(transcribing, { type: 'PARTIAL', text: 'Deploy the' })
    expect(partial.partialTranscript).toBe('Deploy the')

    const confirming = voiceReducer(partial, { type: 'FINAL', text: 'Deploy the service' })
    expect(confirming.phase).toBe('confirming')
    expect(confirming.transcript).toBe('Deploy the service')

    const planning = voiceReducer(confirming, { type: 'CONFIRM', mode: 'plan' })
    expect(planning.phase).toBe('planning')
    expect(planning.caption).toContain('план')
  })

  it('confirm in ask mode uses ask caption', () => {
    const confirming = {
      ...initialVoiceState,
      phase: 'confirming' as const,
      transcript: 'Что в очереди?',
      voiceRequireConfirm: true,
    }
    const planning = voiceReducer(confirming, { type: 'CONFIRM', mode: 'ask' })
    expect(planning.phase).toBe('planning')
    expect(planning.caption).toContain('Спрашиваю')
  })

  it('confirm in do mode uses do caption', () => {
    const confirming = {
      ...initialVoiceState,
      phase: 'confirming' as const,
      transcript: 'Почини баг',
      voiceRequireConfirm: true,
    }
    const planning = voiceReducer(confirming, { type: 'CONFIRM', mode: 'do' })
    expect(planning.phase).toBe('planning')
    expect(planning.caption).toContain('действие')
  })

  it('auto-dispatches to planning when confirm is disabled', () => {
    const listening = voiceReducer(initialVoiceState, { type: 'START_LISTENING', at: 1 })
    const done = voiceReducer(listening, { type: 'FINAL', text: 'Fix the deploy' })
    expect(done.phase).toBe('planning')
    expect(done.transcript).toBe('Fix the deploy')
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

  it('returns to planning after milestone playback', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Статус',
      mode: 'ask',
    })
    const speaking = voiceReducer(planning, {
      type: 'SPEAKING',
      caption: 'Взял. Cloud.',
      kind: 'milestone',
    })
    expect(speaking.phase).toBe('speaking')
    expect(speaking.speakingKind).toBe('milestone')
    const back = voiceReducer(speaking, { type: 'PLAYBACK_DONE' })
    expect(back.phase).toBe('planning')
    expect(back.speakingKind).toBeNull()
    expect(back.caption).toContain('Взял')
  })

  it('returns to idle after final playback', () => {
    const speaking = voiceReducer(initialVoiceState, {
      type: 'SPEAKING',
      caption: 'Готово.',
      kind: 'final',
    })
    const idle = voiceReducer(speaking, { type: 'PLAYBACK_DONE' })
    expect(idle.phase).toBe('idle')
    expect(idle.speakingKind).toBeNull()
  })
})
