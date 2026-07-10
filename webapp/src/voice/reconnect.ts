/** Close codes that must not trigger automatic reconnect. */
export const VOICE_FATAL_CLOSE_CODES = new Set([
  4401, // unauthorized / invalid Telegram initData
  4429, // voice session rate limited
])

/** Server error codes that must stop the reconnect loop even if the close code is mangled to 1006. */
export const VOICE_FATAL_ERROR_CODES = new Set([
  'unauthorized',
  'rate_limited',
])

export const VOICE_RECONNECT_LIMIT = 8

export function shouldReconnectVoice(options: {
  intentionallyClosed: boolean
  online: boolean
  closeCode: number
  attempts: number
  fatalFailure?: boolean
  limit?: number
}): boolean {
  if (options.intentionallyClosed || !options.online) return false
  if (options.fatalFailure) return false
  if (VOICE_FATAL_CLOSE_CODES.has(options.closeCode)) return false
  const limit = options.limit ?? VOICE_RECONNECT_LIMIT
  return options.attempts < limit
}

export function isFatalVoiceErrorCode(code: string | undefined): boolean {
  return Boolean(code && VOICE_FATAL_ERROR_CODES.has(code))
}

export function voiceReconnectDelayMs(attempt: number, random = Math.random()): number {
  return Math.min(12_000, 600 * 2 ** attempt) + random * 250
}
