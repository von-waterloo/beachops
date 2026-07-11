import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  consumeTelegramAuthResult,
  telegramOauthUrl,
} from './auth'

function encodeTgAuthResult(payload: Record<string, unknown>): string {
  const json = JSON.stringify(payload)
  return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

describe('consumeTelegramAuthResult', () => {
  const replaceState = vi.fn()

  beforeEach(() => {
    replaceState.mockReset()
    vi.stubGlobal('history', { replaceState })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('parses #tgAuthResult and clears the hash', () => {
    const encoded = encodeTgAuthResult({
      id: 42,
      first_name: 'Owner',
      username: 'owner',
      auth_date: 1_700_000_000,
      hash: 'a'.repeat(64),
    })
    const href = `https://beachops.marketolog.tech/#tgAuthResult=${encoded}`
    vi.stubGlobal('location', new URL(href))

    const user = consumeTelegramAuthResult(href)

    expect(user).toEqual({
      id: 42,
      first_name: 'Owner',
      username: 'owner',
      auth_date: 1_700_000_000,
      hash: 'a'.repeat(64),
    })
    expect(replaceState).toHaveBeenCalled()
  })

  it('returns null for garbage payload', () => {
    expect(consumeTelegramAuthResult('https://x.test/#tgAuthResult=!!!')).toBeNull()
  })
})

describe('telegramOauthUrl', () => {
  it('builds same-window oauth url without embed', () => {
    vi.stubGlobal('location', {
      href: 'https://beachops.marketolog.tech/',
    })
    const url = telegramOauthUrl({
      botUsername: 'cursor_mt_bot',
      botId: 8414100148,
      loginEnabled: true,
      origin: 'https://beachops.marketolog.tech',
      expectedHost: 'beachops.marketolog.tech',
    })
    expect(url).toContain('https://oauth.telegram.org/auth?')
    expect(url).toContain('bot_id=8414100148')
    expect(url).toContain('origin=https%3A%2F%2Fbeachops.marketolog.tech')
    expect(url).not.toContain('embed=')
  })
})
