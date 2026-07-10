import { afterEach, describe, expect, it, vi } from 'vitest'
import { getTelegramInitData, isTelegramWebApp } from './telegram'

describe('isTelegramWebApp', () => {
  afterEach(() => {
    delete window.Telegram
  })

  it('returns false for the sandbox stub that telegram-web-app.js injects outside Telegram', () => {
    // The official script defines window.Telegram.WebApp with working
    // ready()/expand() no-ops even in a plain browser tab, so their mere
    // presence must not be mistaken for "running inside Telegram".
    window.Telegram = {
      WebApp: {
        initData: '',
        ready: vi.fn(),
        expand: vi.fn(),
      },
    }

    expect(isTelegramWebApp()).toBe(false)
    expect(getTelegramInitData()).toBe('')
  })

  it('returns true once Telegram injects real initData', () => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=abc&user=%7B%22id%22%3A7%7D&hash=signed',
        ready: vi.fn(),
        expand: vi.fn(),
      },
    }

    expect(isTelegramWebApp()).toBe(true)
  })

  it('returns false when the Telegram SDK never loaded at all', () => {
    expect(isTelegramWebApp()).toBe(false)
  })
})
