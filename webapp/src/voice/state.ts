export type VoicePhase =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'confirming'
  | 'planning'
  | 'speaking'
  | 'error'

export interface VoiceState {
  phase: VoicePhase
  partialTranscript: string
  transcript: string
  caption: string
  error: string | null
  connected: boolean
  recordingStartedAt: number | null
}

export const initialVoiceState: VoiceState = {
  phase: 'idle',
  partialTranscript: '',
  transcript: '',
  caption: 'Tap the orb to speak',
  error: null,
  connected: false,
  recordingStartedAt: null,
}

export type VoiceAction =
  | { type: 'CONNECTED'; connected: boolean }
  | { type: 'START_LISTENING'; at: number }
  | { type: 'STOP_LISTENING' }
  | { type: 'PARTIAL'; text: string }
  | { type: 'FINAL'; text: string }
  | { type: 'EDIT'; text: string }
  | { type: 'CONFIRM' }
  | { type: 'SUBMIT_TEXT'; text: string }
  | { type: 'SPEAKING'; caption?: string }
  | { type: 'PLAYBACK_DONE' }
  | { type: 'CANCEL' }
  | { type: 'FAIL'; message: string }
  | { type: 'RESET' }

export function voiceReducer(state: VoiceState, action: VoiceAction): VoiceState {
  switch (action.type) {
    case 'CONNECTED':
      return { ...state, connected: action.connected }
    case 'START_LISTENING':
      return {
        ...initialVoiceState,
        connected: state.connected,
        phase: 'listening',
        recordingStartedAt: action.at,
        caption: 'Listening · microphone active',
      }
    case 'STOP_LISTENING':
      if (state.phase !== 'listening') return state
      return {
        ...state,
        phase: 'transcribing',
        recordingStartedAt: null,
        caption: 'Finishing transcript…',
      }
    case 'PARTIAL':
      if (!['listening', 'transcribing'].includes(state.phase)) return state
      return { ...state, partialTranscript: action.text, caption: action.text }
    case 'FINAL':
      return {
        ...state,
        phase: 'confirming',
        transcript: action.text,
        partialTranscript: '',
        recordingStartedAt: null,
        caption: 'Review before planning',
      }
    case 'EDIT':
      if (state.phase !== 'confirming') return state
      return { ...state, transcript: action.text }
    case 'CONFIRM':
      if (state.phase !== 'confirming' || !state.transcript.trim()) return state
      return { ...state, phase: 'planning', caption: 'Building a safe plan…' }
    case 'SUBMIT_TEXT':
      if (!['idle', 'error', 'confirming'].includes(state.phase) || !action.text.trim()) {
        return state
      }
      return {
        ...state,
        phase: 'planning',
        transcript: action.text.trim(),
        partialTranscript: '',
        error: null,
        caption: 'Building a safe plan…',
      }
    case 'SPEAKING':
      return { ...state, phase: 'speaking', caption: action.caption ?? 'BeachOps is responding' }
    case 'PLAYBACK_DONE':
      if (state.phase !== 'speaking') return state
      return { ...initialVoiceState, connected: state.connected }
    case 'CANCEL':
      return { ...initialVoiceState, connected: state.connected }
    case 'FAIL':
      return {
        ...state,
        phase: 'error',
        error: action.message,
        recordingStartedAt: null,
        caption: action.message,
      }
    case 'RESET':
      return { ...initialVoiceState, connected: state.connected }
  }
}
