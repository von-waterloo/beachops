export type VoiceAgentMode = 'ask' | 'plan' | 'do'

export type VoicePhase =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'confirming'
  | 'planning'
  | 'speaking'
  | 'error'

export type SpeakingKind = 'milestone' | 'final'

export interface VoiceState {
  phase: VoicePhase
  partialTranscript: string
  transcript: string
  caption: string
  error: string | null
  connected: boolean
  recordingStartedAt: number | null
  /** Mid-run TTS returns to planning; final returns to idle. */
  speakingKind: SpeakingKind | null
  /** When false, FINAL auto-dispatches without confirming UI. */
  voiceRequireConfirm: boolean
}

export const initialVoiceState: VoiceState = {
  phase: 'idle',
  partialTranscript: '',
  transcript: '',
  caption: 'Коснись орба — говори',
  error: null,
  connected: false,
  recordingStartedAt: null,
  speakingKind: null,
  voiceRequireConfirm: false,
}

export type VoiceAction =
  | { type: 'CONNECTED'; connected: boolean; voiceRequireConfirm?: boolean }
  | { type: 'START_LISTENING'; at: number }
  | { type: 'STOP_LISTENING' }
  | { type: 'PARTIAL'; text: string }
  | { type: 'FINAL'; text: string }
  | { type: 'EDIT'; text: string }
  | { type: 'CONFIRM'; mode?: VoiceAgentMode }
  | { type: 'SUBMIT_TEXT'; text: string; mode?: VoiceAgentMode }
  | { type: 'PLAN_STARTED'; mode?: VoiceAgentMode }
  | { type: 'PROGRESS'; caption: string }
  | { type: 'SPEAKING'; caption?: string; kind?: SpeakingKind }
  | { type: 'PLAYBACK_DONE' }
  | { type: 'CANCEL' }
  | { type: 'FAIL'; message: string }
  | { type: 'RESET' }

function captionForMode(mode: VoiceAgentMode | undefined, kind: 'submit' | 'started'): string {
  if (kind === 'submit') {
    if (mode === 'ask') return 'Спрашиваю агента. Учитываю очередь и статус control room.'
    if (mode === 'do') return 'Запускаю действие. Пишу в выбранную ветку.'
    return 'Строю план. Без записи в репо.'
  }
  if (mode === 'ask') return 'Агент в эфире. Жду ответ с учётом control room.'
  if (mode === 'do') return 'Действие в очереди. Слежу за прогрессом.'
  return 'План в очереди. Слежу за прогрессом.'
}

export function voiceReducer(state: VoiceState, action: VoiceAction): VoiceState {
  switch (action.type) {
    case 'CONNECTED':
      return {
        ...state,
        connected: action.connected,
        voiceRequireConfirm:
          action.voiceRequireConfirm ?? state.voiceRequireConfirm,
      }
    case 'START_LISTENING':
      return {
        ...initialVoiceState,
        connected: state.connected,
        voiceRequireConfirm: state.voiceRequireConfirm,
        phase: 'listening',
        recordingStartedAt: action.at,
        caption: 'Слушаю. Канал открыт.',
      }
    case 'STOP_LISTENING':
      if (state.phase !== 'listening') return state
      return {
        ...state,
        phase: 'transcribing',
        recordingStartedAt: null,
        caption: 'Разбираю речь…',
      }
    case 'PARTIAL':
      if (!['listening', 'transcribing'].includes(state.phase)) return state
      return { ...state, partialTranscript: action.text, caption: action.text }
    case 'FINAL':
      if (!state.voiceRequireConfirm) {
        return {
          ...state,
          phase: 'planning',
          transcript: action.text,
          partialTranscript: '',
          recordingStartedAt: null,
          speakingKind: null,
          caption: 'Отправляю. Учитываю control room.',
        }
      }
      return {
        ...state,
        phase: 'confirming',
        transcript: action.text,
        partialTranscript: '',
        recordingStartedAt: null,
        speakingKind: null,
        caption: 'Проверь текст и режим перед отправкой',
      }
    case 'EDIT':
      if (state.phase !== 'confirming') return state
      return { ...state, transcript: action.text }
    case 'CONFIRM': {
      if (state.phase !== 'confirming' || !state.transcript.trim()) return state
      return {
        ...state,
        phase: 'planning',
        caption: captionForMode(action.mode, 'submit'),
      }
    }
    case 'SUBMIT_TEXT': {
      if (!['idle', 'error', 'confirming'].includes(state.phase) || !action.text.trim()) {
        return state
      }
      return {
        ...state,
        phase: 'planning',
        transcript: action.text.trim(),
        partialTranscript: '',
        error: null,
        speakingKind: null,
        caption: captionForMode(action.mode, 'submit'),
      }
    }
    case 'PLAN_STARTED': {
      if (state.phase === 'planning') {
        return {
          ...state,
          caption: captionForMode(action.mode, 'started'),
        }
      }
      if (state.phase === 'confirming' && state.transcript.trim()) {
        return {
          ...state,
          phase: 'planning',
          speakingKind: null,
          caption: captionForMode(action.mode, 'started'),
        }
      }
      return state
    }
    case 'PROGRESS':
      if (!['planning', 'speaking'].includes(state.phase)) return state
      return { ...state, caption: action.caption }
    case 'SPEAKING':
      return {
        ...state,
        phase: 'speaking',
        caption: action.caption ?? state.caption ?? 'BeachOps докладывает',
        speakingKind: action.kind ?? state.speakingKind ?? 'final',
      }
    case 'PLAYBACK_DONE':
      if (state.phase !== 'speaking') return state
      if (state.speakingKind === 'milestone') {
        return {
          ...state,
          phase: 'planning',
          speakingKind: null,
          caption: state.caption || 'В эфире. Жду следующий статус.',
        }
      }
      return {
        ...initialVoiceState,
        connected: state.connected,
        voiceRequireConfirm: state.voiceRequireConfirm,
      }
    case 'CANCEL':
      return {
        ...initialVoiceState,
        connected: state.connected,
        voiceRequireConfirm: state.voiceRequireConfirm,
      }
    case 'FAIL':
      return {
        ...state,
        phase: 'error',
        error: action.message,
        recordingStartedAt: null,
        speakingKind: null,
        caption: action.message,
      }
    case 'RESET':
      return {
        ...initialVoiceState,
        connected: state.connected,
        voiceRequireConfirm: state.voiceRequireConfirm,
      }
  }
}
