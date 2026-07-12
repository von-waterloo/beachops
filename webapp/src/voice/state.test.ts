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

    const transcribing = voiceReducer(listening, { type: 'STOP_LISTENING' })
    expect(transcribing.phase).toBe('transcribing')

    const confirming = voiceReducer(transcribing, { type: 'FINAL', text: 'Deploy the service' })
    expect(confirming.phase).toBe('confirming')

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
    expect(planning.caption).toContain('Делаю')
  })

  it('queues additional text while planning', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Первая',
      mode: 'ask',
    })
    const queued = voiceReducer(planning, {
      type: 'SUBMIT_TEXT',
      text: 'Вторая',
      mode: 'ask',
    })
    expect(queued.phase).toBe('planning')
    expect(queued.transcript).toBe('Вторая')
    expect(queued.queuedHint).toContain('очереди')
  })

  it('auto-dispatches to planning when confirm is disabled', () => {
    const listening = voiceReducer(initialVoiceState, { type: 'START_LISTENING', at: 1 })
    const done = voiceReducer(listening, {
      type: 'FINAL',
      text: 'Fix the deploy',
      mode: 'ask',
    })
    expect(done.phase).toBe('planning')
    expect(done.caption).toContain('Спрашиваю')
  })

  it('returns to idle after final playback', () => {
    const speaking = voiceReducer(initialVoiceState, {
      type: 'SPEAKING',
      caption: 'Готово.',
      kind: 'final',
    })
    const idle = voiceReducer(speaking, { type: 'PLAYBACK_DONE' })
    expect(idle.phase).toBe('idle')
  })

  it('returns to planning after milestone playback', () => {
    const planning = voiceReducer(initialVoiceState, {
      type: 'SUBMIT_TEXT',
      text: 'Статус',
      mode: 'ask',
    })
    const speaking = voiceReducer(planning, {
      type: 'SPEAKING',
      caption: 'Ок, беру.',
      kind: 'milestone',
    })
    const back = voiceReducer(speaking, { type: 'PLAYBACK_DONE' })
    expect(back.phase).toBe('planning')
  })
})
