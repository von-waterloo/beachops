import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { getTelegramInitData } from '../lib/telegram'
import { feedback } from '../lib/feedback'
import { voiceWebSocketUrl } from '../lib/api'
import {
  shouldReconnectVoice,
  voiceReconnectDelayMs,
  VOICE_FATAL_CLOSE_CODES,
  VOICE_RECONNECT_LIMIT,
} from './reconnect'
import { initialVoiceState, voiceReducer } from './state'

const MAX_RECORDING_MS = 60_000
const AUTH_FAILED = 'Сессия истекла или недействительна'
const RATE_LIMITED = 'Слишком много голосовых сессий — подождите немного'

interface VoiceEvent {
  type: string
  seq?: number
  eventId?: string
  text?: string
  caption?: string
  message?: string
  code?: string
  jobId?: string
  mode?: string
  kind?: string
  voiceRequireConfirm?: boolean
}

const VOICE_ERROR_MESSAGES: Record<string, string> = {
  provider_unavailable: 'Голосовой сервис недоступен',
  chunk_too_large: 'Слишком большой аудио-чанк',
  session_limit: 'Лимит голосовой сессии исчерпан',
  invalid_event: 'Некорректное голосовое событие',
  invalid_transcript: 'Пустой или слишком длинный транскрипт',
  job_missing: 'Задача исчезла',
  missing_run_id: 'Задача завершилась без run id',
  memory_missing: 'Результат задачи ещё не готов',
  no_repository: 'Сначала выберите репозиторий',
  dispatch_blocked: 'Запрос заблокирован политикой',
}

function voiceErrorMessage(event: VoiceEvent): string {
  if (event.message?.trim()) return event.message.trim()
  if (event.code && VOICE_ERROR_MESSAGES[event.code]) {
    return VOICE_ERROR_MESSAGES[event.code]
  }
  if (event.code) return `Ошибка голоса: ${event.code}`
  return 'Голосовой сервис недоступен'
}

export function useVoiceSession(options: {
  onJobStarted?: (jobId: string) => void
} = {}) {
  const [state, dispatch] = useReducer(voiceReducer, initialVoiceState)
  const [energy, setEnergy] = useState(0)
  const [spectrum, setSpectrum] = useState<number[]>(() => Array(24).fill(0.04))
  const wsRef = useRef<WebSocket | null>(null)
  const workletRef = useRef<AudioWorkletNode | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationRef = useRef(0)
  const maxDurationRef = useRef<number | undefined>(undefined)
  const seqRef = useRef(0)
  const chunkSeqRef = useRef(0)
  const seenEventsRef = useRef(new Set<string>())
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | undefined>(undefined)
  const intentionallyClosedRef = useRef(false)
  const connectedRef = useRef(false)
  const playbackQueueRef = useRef<ArrayBuffer[]>([])
  const playingRef = useRef<AudioBufferSourceNode | null>(null)
  const playbackContextRef = useRef<AudioContext | null>(null)
  const onJobStartedRef = useRef(options.onJobStarted)
  const voiceRequireConfirmRef = useRef(false)
  const submitModeRef = useRef<'ask' | 'plan'>('ask')
  onJobStartedRef.current = options.onJobStarted

  useEffect(() => {
    connectedRef.current = state.connected
    voiceRequireConfirmRef.current = state.voiceRequireConfirm
  }, [state.connected, state.voiceRequireConfirm])

  const setSubmitMode = useCallback((mode: 'ask' | 'plan') => {
    submitModeRef.current = mode
  }, [])

  const sendJson = useCallback((payload: Record<string, unknown>) => {
    const socket = wsRef.current
    if (socket?.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify({ ...payload, seq: ++seqRef.current }))
    return true
  }, [])

  const playNext = useCallback(() => {
    if (playingRef.current || playbackQueueRef.current.length === 0) {
      if (!playingRef.current && playbackQueueRef.current.length === 0) {
        dispatch({ type: 'PLAYBACK_DONE' })
      }
      return
    }
    const raw = playbackQueueRef.current.shift()!
    const context = playbackContextRef.current ?? new AudioContext({ sampleRate: 24_000 })
    playbackContextRef.current = context
    const pcm = new Int16Array(raw)
    const buffer = context.createBuffer(1, pcm.length, 24_000)
    const channel = buffer.getChannelData(0)
    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = pcm[index] / 0x8000
    }
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)
    playingRef.current = source
    const finish = () => {
      playingRef.current = null
      playNext()
    }
    source.onended = finish
    source.start()
  }, [])

  const stopPlayback = useCallback(() => {
    const current = playingRef.current
    if (current) {
      current.stop()
      current.disconnect()
      playingRef.current = null
    }
    playbackQueueRef.current = []
  }, [])

  const handleServerEvent = useCallback((event: VoiceEvent) => {
    const identity = event.eventId ?? (event.seq === undefined ? undefined : String(event.seq))
    if (identity && seenEventsRef.current.has(identity)) return
    if (identity) {
      seenEventsRef.current.add(identity)
      if (seenEventsRef.current.size > 500) {
        const oldest = seenEventsRef.current.values().next().value
        if (oldest) seenEventsRef.current.delete(oldest)
      }
    }

    switch (event.type) {
      case 'session.ready':
        reconnectRef.current = 0
        voiceRequireConfirmRef.current = event.voiceRequireConfirm === true
        dispatch({
          type: 'CONNECTED',
          connected: true,
          voiceRequireConfirm: event.voiceRequireConfirm === true,
        })
        break
      case 'transcript.partial':
        dispatch({ type: 'PARTIAL', text: event.text ?? '' })
        break
      case 'transcript.final': {
        const text = event.text ?? ''
        dispatch({ type: 'FINAL', text })
        feedback('success')
        if (!voiceRequireConfirmRef.current && text.trim()) {
          sendJson({
            type: 'plan.request',
            transcript: text.trim(),
            mode: submitModeRef.current,
          })
        }
        break
      }
      case 'plan.started':
        dispatch({
          type: 'PLAN_STARTED',
          mode: event.mode === 'ask' ? 'ask' : 'plan',
        })
        if (event.jobId) onJobStartedRef.current?.(event.jobId)
        break
      case 'job.progress':
        if (event.text?.trim()) {
          dispatch({ type: 'PROGRESS', caption: event.text.trim().slice(0, 280) })
        }
        break
      case 'audio.started':
        dispatch({
          type: 'SPEAKING',
          caption: event.caption,
          kind: event.kind === 'milestone' ? 'milestone' : 'final',
        })
        break
      case 'caption':
        dispatch({ type: 'SPEAKING', caption: event.text })
        break
      case 'audio.ended':
        playNext()
        break
      case 'error':
        dispatch({ type: 'FAIL', message: voiceErrorMessage(event) })
        feedback('error')
        break
    }
  }, [playNext, sendJson])

  const connect = useCallback(() => {
    if (!navigator.onLine) return
    const existing = wsRef.current
    if (
      existing
      && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    const initData = getTelegramInitData()

    intentionallyClosedRef.current = false
    window.clearTimeout(reconnectTimerRef.current)
    const socket = new WebSocket(voiceWebSocketUrl())
    socket.binaryType = 'blob'
    wsRef.current = socket
    socket.onopen = () => {
      // Do not mark connected or reset reconnect budget until session.ready —
      // TCP open alone can still fail auth and must not loop forever.
      socket.send(JSON.stringify({
        type: 'authenticate',
        authorization: initData ? `tma ${initData}` : 'session',
        seq: ++seqRef.current,
      }))
    }
    socket.onmessage = (message) => {
      if (message.data instanceof Blob) {
        void message.data.arrayBuffer().then((audio) => {
          playbackQueueRef.current.push(audio)
          dispatch({ type: 'SPEAKING' })
          playNext()
        })
        return
      }
      try {
        handleServerEvent(JSON.parse(message.data) as VoiceEvent)
      } catch {
        dispatch({ type: 'FAIL', message: 'Получено некорректное голосовое событие' })
      }
    }
    socket.onerror = () => socket.close()
    socket.onclose = (event) => {
      if (wsRef.current && wsRef.current !== socket) return
      dispatch({ type: 'CONNECTED', connected: false })
      wsRef.current = null

      if (VOICE_FATAL_CLOSE_CODES.has(event.code)) {
        dispatch({
          type: 'FAIL',
          message: event.code === 4429 ? RATE_LIMITED : AUTH_FAILED,
        })
        feedback('error')
        return
      }

      if (
        !shouldReconnectVoice({
          intentionallyClosed: intentionallyClosedRef.current,
          online: navigator.onLine,
          closeCode: event.code,
          attempts: reconnectRef.current,
          limit: VOICE_RECONNECT_LIMIT,
        })
      ) {
        if (!intentionallyClosedRef.current && navigator.onLine) {
          dispatch({ type: 'FAIL', message: 'Не удалось переподключиться к голосу' })
        }
        return
      }

      const attempt = reconnectRef.current++
      const delay = voiceReconnectDelayMs(attempt)
      reconnectTimerRef.current = window.setTimeout(connect, delay)
    }
  }, [handleServerEvent, playNext])

  // Lazy connect: open WS only when the user starts talking / sends text.
  // Eager connect on mount burned the rate limit on every tab remount.
  useEffect(() => {
    const offline = () => {
      dispatch({ type: 'CONNECTED', connected: false })
      dispatch({ type: 'FAIL', message: 'Нет сети' })
    }
    const online = () => {
      // Do not auto-reconnect on online — wait for the next user action.
    }
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      intentionallyClosedRef.current = true
      window.clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
      void playbackContextRef.current?.close()
      playbackContextRef.current = null
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [])

  const stopCapture = useCallback((notifyServer = true) => {
    window.clearTimeout(maxDurationRef.current)
    cancelAnimationFrame(animationRef.current)
    workletRef.current?.disconnect()
    workletRef.current = null
    if (notifyServer) {
      sendJson({ type: 'audio.end', chunks: chunkSeqRef.current })
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
    void audioContextRef.current?.close()
    audioContextRef.current = null
    setEnergy(0)
  }, [sendJson])

  const startListening = useCallback(async () => {
    if (!navigator.onLine) {
      dispatch({ type: 'FAIL', message: 'Подключитесь к сети, чтобы говорить' })
      return
    }
    if (wsRef.current?.readyState !== WebSocket.OPEN || !state.connected) {
      connect()
      // Wait briefly for session.ready instead of forcing a second tap.
      for (let i = 0; i < 25; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 120))
        if (connectedRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
          break
        }
      }
      if (!connectedRef.current || wsRef.current?.readyState !== WebSocket.OPEN) {
        dispatch({
          type: 'FAIL',
          message: 'Не удалось открыть голосовой канал. Попробуй ещё раз.',
        })
        return
      }
    }

    try {
      stopPlayback()
      sendJson({ type: 'barge_in' })
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      mediaStreamRef.current = stream
      const context = new AudioContext({ latencyHint: 'interactive' })
      audioContextRef.current = context
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = 128
      analyser.smoothingTimeConstant = 0.72
      source.connect(analyser)

      const values = new Uint8Array(analyser.frequencyBinCount)
      const lowPower = (navigator.hardwareConcurrency || 8) <= 4
      let lastPaint = 0
      const sample = (now: number) => {
        animationRef.current = requestAnimationFrame(sample)
        if (now - lastPaint < (lowPower ? 100 : 32)) return
        lastPaint = now
        analyser.getByteFrequencyData(values)
        const bands = Array.from({ length: 24 }, (_, index) => {
          const value = values[Math.floor(index * values.length / 24)] ?? 0
          return Math.max(0.035, value / 255)
        })
        setSpectrum(bands)
        setEnergy(bands.reduce((total, value) => total + value, 0) / bands.length)
      }
      animationRef.current = requestAnimationFrame(sample)

      await context.audioWorklet.addModule('/pcm-worklet.js')
      const worklet = new AudioWorkletNode(context, 'beachops-pcm')
      const silentGain = context.createGain()
      silentGain.gain.value = 0
      source.connect(worklet)
      worklet.connect(silentGain)
      silentGain.connect(context.destination)
      workletRef.current = worklet
      worklet.port.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => {
        if (data.byteLength && wsRef.current?.readyState === WebSocket.OPEN) {
          chunkSeqRef.current += 1
          wsRef.current.send(data)
        }
      }
      chunkSeqRef.current = 0
      sendJson({ type: 'audio.start', codec: 'audio/pcm', sampleRate: 24_000 })
      dispatch({ type: 'START_LISTENING', at: Date.now() })
      feedback('tap')
      maxDurationRef.current = window.setTimeout(() => {
        stopCapture()
        dispatch({ type: 'STOP_LISTENING' })
        feedback('warning')
      }, MAX_RECORDING_MS)
    } catch (error) {
      const denied = error instanceof DOMException && error.name === 'NotAllowedError'
      dispatch({
        type: 'FAIL',
        message: denied ? 'Нужен доступ к микрофону' : 'Микрофон недоступен',
      })
      feedback('error')
    }
  }, [connect, sendJson, state.connected, stopCapture, stopPlayback])
  const finishListening = useCallback(() => {
    stopCapture()
    dispatch({ type: 'STOP_LISTENING' })
    feedback('tap')
  }, [stopCapture])

  const cancel = useCallback(() => {
    stopCapture(false)
    stopPlayback()
    sendJson({ type: 'session.cancel' })
    dispatch({ type: 'CANCEL' })
    feedback('select')
  }, [sendJson, stopCapture, stopPlayback])

  const confirmSubmit = useCallback((mode: 'ask' | 'plan' = submitModeRef.current) => {
    if (!state.transcript.trim()) return
    submitModeRef.current = mode
    sendJson({ type: 'plan.request', transcript: state.transcript.trim(), mode })
    dispatch({ type: 'CONFIRM', mode })
    feedback('success')
  }, [sendJson, state.transcript])

  const submitComposer = useCallback((text: string, mode: 'ask' | 'plan' = 'ask') => {
    const trimmed = text.trim()
    if (!trimmed) return false
    if (!navigator.onLine) {
      dispatch({ type: 'FAIL', message: 'Подключитесь к сети, чтобы отправить запрос' })
      return false
    }
    if (wsRef.current?.readyState !== WebSocket.OPEN || !state.connected) {
      connect()
      dispatch({
        type: 'FAIL',
        message: 'Подключаю голос… отправь ещё раз через секунду',
      })
      return false
    }
    submitModeRef.current = mode
    sendJson({ type: 'plan.request', transcript: trimmed, mode })
    dispatch({ type: 'SUBMIT_TEXT', text: trimmed, mode })
    feedback('success')
    return true
  }, [connect, sendJson, state.connected])

  return {
    state,
    energy,
    spectrum,
    startListening,
    finishListening,
    cancel,
    confirmSubmit,
    submitComposer,
    setSubmitMode,
    editTranscript: (text: string) => dispatch({ type: 'EDIT', text }),
    reset: () => dispatch({ type: 'RESET' }),
  }
}
