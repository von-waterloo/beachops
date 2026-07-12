import { describe, expect, it } from 'vitest'
import { PcmStreamPlayer } from './pcmPlayer'

describe('PcmStreamPlayer', () => {
  it('accepts enqueue without throwing on empty buffer', () => {
    const player = new PcmStreamPlayer()
    expect(() => player.enqueue(new ArrayBuffer(0))).not.toThrow()
    player.stop()
  })

  it('stop clears pending without touching AudioContext', () => {
    const player = new PcmStreamPlayer()
    player.enqueue(new Uint8Array([0, 0, 1, 2]).buffer)
    expect(() => player.stop()).not.toThrow()
  })
})
