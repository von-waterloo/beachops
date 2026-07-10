import { describe, expect, it } from 'vitest'
import { matchesRuntimeFilter } from './runtimeFilter'

describe('matchesRuntimeFilter', () => {
  it('lets everything through for all', () => {
    expect(matchesRuntimeFilter('cloud', 'all')).toBe(true)
    expect(matchesRuntimeFilter('windows', 'all')).toBe(true)
    expect(matchesRuntimeFilter(null, 'all')).toBe(true)
  })

  it('keeps only windows for windows filter', () => {
    expect(matchesRuntimeFilter('windows', 'windows')).toBe(true)
    expect(matchesRuntimeFilter('cloud', 'windows')).toBe(false)
    expect(matchesRuntimeFilter(undefined, 'windows')).toBe(false)
  })

  it('treats non-windows as cloud', () => {
    expect(matchesRuntimeFilter('cloud', 'cloud')).toBe(true)
    expect(matchesRuntimeFilter(null, 'cloud')).toBe(true)
    expect(matchesRuntimeFilter('windows', 'cloud')).toBe(false)
  })
})
