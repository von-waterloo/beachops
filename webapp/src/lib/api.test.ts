import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './api'

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    delete window.Telegram
  })

  it('sends raw Telegram initData in the Authorization header', async () => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=abc&user=%7B%22id%22%3A7%7D&hash=signed',
        ready: vi.fn(),
        expand: vi.fn(),
      },
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch<{ ok: boolean }>('/api/jobs')

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(request.headers)
    expect(headers.get('Authorization')).toBe(
      'tma query_id=abc&user=%7B%22id%22%3A7%7D&hash=signed',
    )
  })

  it('uses the secure browser session when Telegram initData is absent', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch<{ ok: boolean }>('/api/me')

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(request.headers)
    expect(headers.has('Authorization')).toBe(false)
    expect(request.credentials).toBe('same-origin')
  })
})
