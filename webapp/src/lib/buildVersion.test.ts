import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ensureFreshWebappBuild } from './buildVersion'

describe('ensureFreshWebappBuild', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('stores build id on first load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => 'abc123\n',
    }))
    await ensureFreshWebappBuild()
    expect(localStorage.getItem('beachops-build-id')).toBe('abc123')
  })

  it('reloads when build id changes', async () => {
    localStorage.setItem('beachops-build-id', 'old')
    const reload = vi.fn()
    vi.stubGlobal('location', { reload })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => 'new456',
    }))
    await ensureFreshWebappBuild()
    expect(reload).toHaveBeenCalledOnce()
    expect(localStorage.getItem('beachops-build-id')).toBe('new456')
  })
})
