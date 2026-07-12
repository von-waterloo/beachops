import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { getTelegramInitData } from '../lib/telegram'
import { feedback } from '../lib/feedback'
import { voiceWebSocketUrl } from '../lib/api'
import {
  isFatalVoiceErrorCode,
  shouldReconnectVoice,
  voiceReconnectDelayMs,
  VOICE_FATAL_CLOSE_CODES,
  VOICE_RECONNECT_LIMIT,
} from './reconnect'
import { SPECTRUM_BAR_COUNT } from './constants'
import { PcmStreamPlayer } from './pcmPlayer'
import { initialVoiceState, voiceReducer } from './state'

const MAX_RECORDING_MS = 60_000
const PING_INTERVAL_MS = 25_000
/** PCM16 mono @ 24 kHz — OpenAI needs ≥100ms before commit. */
const MIN_AUDIO_BYTES = 24_000 * 2 / 10
const AUTH_FAILED = 'Session expired or invalid'
const RATE_LIMITED = 'Voice session rate limited — try again shortly'
const TOO_SHORT =
  'Слишком коротко — подержите кнопку и говорите не меньше секунды.'

interface VoiceEvent {
  type: string
  seq?: number
  eventId?: string
  text?: string
  caption?: string
  message?: string
  code?: string
}

const VOICE_ERROR_MESSAGES: Record<string, string> = {
  provider_unavailable: 'Voice service unavailable',
  chunk_too_large: 'Audio chunk too large',
  session_limit: 'Voice session limit reached',
  invalid_event: 'Invalid voice event',
  invalid_transcript: 'Transcript is empty or too long',
  empty_audio: TOO_SHORT,
  job_missing: 'Task disappeared',
  missing_run_id: 'Task finished without a run id',
  memory_missing: 'Task result is not ready yet',
  no_repository: 'Select a repository first',
  dispatch_blocked: 'Request blocked',
  unauthorized: AUTH_FAILED,
  rate_limited: RATE_LIMITED,
}

function voiceErrorMessage(event: VoiceEvent): string {
  if (event.message?.trim()) return event.message.trim()
  if (event.code && VOICE_ERROR_MESSAGES[event.code]) {
    return VOICE_ERROR_MESSAGES[event.code]
  }
  if (event.code) return `Voice error: ${event.code}`
  return 'Voice service unavailable'
}

export function useVoiceSession() {
  const [state, dispatch] = useReducer(voiceReducer, initialVoiceState)
  const [energy, setEnergy] = useState(0)
  const [spectrum, setSpectrum] = useState<number[]>(() => Array(SPECTRUM_BAR_COUNT).fill(0.04))
  const wsRef = useRef<WebSocket | null>(null)
  const workletRef = useRef<AudioWorkletNode | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationRef = useRef(0)
  const maxDurationRef = useRef<number | undefined>(undefined)
  const seqRef = useRef(0)
  const chunkSeqRef = useRef(0)
  const bytesSentRef = useRef(0)
  const seenEventsRef = useRef(new Set<string>())
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | undefined>(undefined)
  const pingTimerRef = useRef<number | undefined>(undefined)
  const intentionallyClosedRef = useRef(false)
  const fatalFailureRef = useRef(false)
  const pcmPlayerRef = useRef<PcmStreamPlayer | null>(null)

  useEffect(() => {
    pcmPlayerRef.current = new PcmStreamPlayer(() => {
      dispatch({ type: 'PLAYBACK_DONE' })
    })
    return () => {
      pcmPlayerRef.current?.stop()
      pcmPlayerRef.current = null
    }
  }, [])

  const clearPing = useCallback(() => {
    window.clearInterval(pingTimerRef.current)
    pingTimerRef.current = undefined
  }, [])

  const sendJson = useCallback((payload: Record<string, unknown>) => {
    const socket = wsRef.current
    if (socket?.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify({ ...payload, seq: ++seqRef.current }))
    return true
  }, [])

  const stopPlayback = useCallback(() => {
    pcmPlayerRef.current?.stop()
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
        fatalFailureRef.current = false
        dispatch({ type: 'CONNECTED', connected: true })
        break
      case 'pong':
        break
      case 'transcript.partial':
        dispatch({ type: 'PARTIAL', text: event.text ?? '' })
        break
      case 'transcript.final':
        dispatch({ type: 'FINAL', text: event.text ?? '' })
        feedback('success')
        break
      case 'plan.started':
        dispatch({ type: 'CONFIRM' })
        break
      case 'audio.started':
        dispatch({ type: 'SPEAKING', caption: event.caption })
        break
      case 'caption':
        dispatch({ type: 'SPEAKING', caption: event.text })
        break
      case 'audio.ended':
        pcmPlayerRef.current?.flush()
        break
      case 'error':
        if (isFatalVoiceErrorCode(event.code)) {
          fatalFailureRef.current = true
        }
        dispatch({ type: 'FAIL', message: voiceErrorMessage(event) })
        feedback('error')
        break
    }
  }, [])

  const connect = useCallback(() => {
    if (!navigator.onLine || fatalFailureRef.current) return
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
    clearPing()
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
      clearPing()
      pingTimerRef.current = window.setInterval(() => {
        if (wsRef.current === socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'ping', seq: ++seqRef.current }))
        }
      }, PING_INTERVAL_MS)
    }
    socket.onmessage = (message) => {
      if (message.data instanceof Blob) {
        void message.data.arrayBuffer().then((audio) => {
          pcmPlayerRef.current?.enqueue(audio)
          dispatch({ type: 'SPEAKING' })
        })
        return
      }
      try {
        handleServerEvent(JSON.parse(message.data) as VoiceEvent)
      } catch {
        dispatch({ type: 'FAIL', message: 'Received an invalid voice event' })
      }
    }
    socket.onerror = () => socket.close()
    socket.onclose = (event) => {
      if (wsRef.current && wsRef.current !== socket) return
      clearPing()
      dispatch({ type: 'CONNECTED', connected: false })
      wsRef.current = null

      if (VOICE_FATAL_CLOSE_CODES.has(event.code) || fatalFailureRef.current) {
        fatalFailureRef.current = true
        if (VOICE_FATAL_CLOSE_CODES.has(event.code)) {
          dispatch({
            type: 'FAIL',
            message: event.code === 4429 ? RATE_LIMITED : AUTH_FAILED,
          })
          feedback('error')
        }
        return
      }

      if (
        !shouldReconnectVoice({
          intentionallyClosed: intentionallyClosedRef.current,
          online: navigator.onLine,
          closeCode: event.code,
          attempts: reconnectRef.current,
          fatalFailure: fatalFailureRef.current,
          limit: VOICE_RECONNECT_LIMIT,
        })
      ) {
        if (!intentionallyClosedRef.current && navigator.onLine) {
          dispatch({ type: 'FAIL', message: 'Could not reconnect to voice service' })
        }
        return
      }

      const attempt = reconnectRef.current++
      const delay = voiceReconnectDelayMs(attempt)
      reconnectTimerRef.current = window.setTimeout(connect, delay)
    }
  }, [clearPing, handleServerEvent])

  useEffect(() => {
    connect()
    const online = () => {
      fatalFailureRef.current = false
      connect()
    }
    const offline = () => {
      clearPing()
      dispatch({ type: 'CONNECTED', connected: false })
      dispatch({ type: 'FAIL', message: 'You are offline' })
    }
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      intentionallyClosedRef.current = true
      window.clearTimeout(reconnectTimerRef.current)
      clearPing()
      wsRef.current?.close()
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [clearPing, connect])

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

  const discardShortCapture = useCallback(() => {
    stopCapture(false)
    sendJson({ type: 'session.cancel' })
    dispatch({ type: 'FAIL', message: TOO_SHORT })
    feedback('warning')
  }, [sendJson, stopCapture])

  const startListening = useCallback(async () => {
    if (!navigator.onLine) {
      dispatch({ type: 'FAIL', message: 'Connect to the internet to use voice' })
      return
    }
    if (wsRef.current?.readyState !== WebSocket.OPEN || !state.connected) {
      fatalFailureRef.current = false
      connect()
      dispatch({ type: 'FAIL', message: 'Voice service is reconnecting' })
      return
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
      // Suspended context = zero PCM → OpenAI "buffer too small … 0.00ms".
      if (context.state === 'suspended') {
        await context.resume()
      }
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
        const bands = Array.from({ length: SPECTRUM_BAR_COUNT }, (_, index) => {
          const value = values[Math.floor(index * values.length / SPECTRUM_BAR_COUNT)] ?? 0
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
          bytesSentRef.current += data.byteLength
          wsRef.current.send(data)
        }
      }
      chunkSeqRef.current = 0
      bytesSentRef.current = 0
      sendJson({ type: 'audio.start', codec: 'audio/pcm', sampleRate: 24_000 })
      dispatch({ type: 'START_LISTENING', at: Date.now() })
      feedback('tap')
      maxDurationRef.current = window.setTimeout(() => {
        if (bytesSentRef.current < MIN_AUDIO_BYTES) {
          discardShortCapture()
          return
        }
        stopCapture(true)
        dispatch({ type: 'STOP_LISTENING' })
        feedback('warning')
      }, MAX_RECORDING_MS)
    } catch (error) {
      const denied = error instanceof DOMException && error.name === 'NotAllowedError'
      dispatch({
        type: 'FAIL',
        message: denied ? 'Microphone permission is required' : 'Microphone is unavailable',
      })
      feedback('error')
    }
  }, [connect, discardShortCapture, sendJson, state.connected, stopCapture, stopPlayback])

  const finishListening = useCallback(() => {
    if (bytesSentRef.current < MIN_AUDIO_BYTES) {
      discardShortCapture()
      return
    }
    stopCapture(true)
    dispatch({ type: 'STOP_LISTENING' })
    feedback('tap')
  }, [discardShortCapture, stopCapture])

  const cancel = useCallback(() => {
    stopCapture(false)
    stopPlayback()
    sendJson({ type: 'session.cancel' })
    dispatch({ type: 'CANCEL' })
    feedback('select')
  }, [sendJson, stopCapture, stopPlayback])

  const confirmPlan = useCallback(() => {
    if (!state.transcript.trim()) return
    sendJson({ type: 'plan.request', transcript: state.transcript.trim() })
    dispatch({ type: 'CONFIRM' })
    feedback('success')
  }, [sendJson, state.transcript])

  const submitComposer = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return false
    if (!navigator.onLine) {
      dispatch({ type: 'FAIL', message: 'Connect to the internet to send a request' })
      return false
    }
    if (wsRef.current?.readyState !== WebSocket.OPEN || !state.connected) {
      fatalFailureRef.current = false
      connect()
      dispatch({ type: 'FAIL', message: 'Voice service is reconnecting' })
      return false
    }
    sendJson({ type: 'plan.request', transcript: trimmed })
    dispatch({ type: 'SUBMIT_TEXT', text: trimmed })
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
    confirmPlan,
    submitComposer,
    editTranscript: (text: string) => dispatch({ type: 'EDIT', text }),
    reset: () => {
      fatalFailureRef.current = false
      dispatch({ type: 'RESET' })
      connect()
    },
  }
}
