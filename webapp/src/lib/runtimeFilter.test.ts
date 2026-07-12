import { describe, expect, it } from 'vitest'
import { matchesRuntimeFilter } from './runtimeFilter'

describe('matchesRuntimeFilter', () => {
  it('shows everything on all', () => {
    expect(matchesRuntimeFilter('cloud', 'all')).toBe(true)
    expect(matchesRuntimeFilter('windows', 'all')).toBe(true)
    expect(matchesRuntimeFilter(null, 'all')).toBe(true)
  })

  it('cloud filter hides legacy windows rows', () => {
    expect(matchesRuntimeFilter('cloud', 'cloud')).toBe(true)
    expect(matchesRuntimeFilter(null, 'cloud')).toBe(true)
    expect(matchesRuntimeFilter('windows', 'cloud')).toBe(false)
  })
})
