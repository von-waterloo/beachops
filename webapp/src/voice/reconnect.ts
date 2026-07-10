/** Close codes that must not trigger automatic reconnect. */
export const VOICE_FATAL_CLOSE_CODES = new Set([
  4401, // unauthorized / invalid Telegram initData
  4429, // voice session rate limited
])

export const VOICE_RECONNECT_LIMIT = 5

export function shouldReconnectVoice(options: {
  intentionallyClosed: boolean
  online: boolean
  closeCode: number
  attempts: number
  limit?: number
}): boolean {
  if (options.intentionallyClosed || !options.online) return false
  if (VOICE_FATAL_CLOSE_CODES.has(options.closeCode)) return false
  const limit = options.limit ?? VOICE_RECONNECT_LIMIT
  return options.attempts < limit
}

export function voiceReconnectDelayMs(attempt: number, random = Math.random()): number {
  return Math.min(8000, 500 * 2 ** attempt) + random * 250
}
