import { afterEach, describe, expect, it } from 'vitest'
import {
  isOnboardingDone,
  markOnboardingDone,
  resetOnboarding,
} from './onboarding'

describe('onboarding storage', () => {
  afterEach(() => {
    resetOnboarding()
  })

  it('starts incomplete and marks done', () => {
    resetOnboarding()
    expect(isOnboardingDone()).toBe(false)
    markOnboardingDone()
    expect(isOnboardingDone()).toBe(true)
  })
})
