import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { PcmStreamPlayer } from './pcmPlayer'

/**
 * Minimal AudioContext fake that records BufferSource `start(when)` times so we
 * can assert gapless scheduling without a real Web Audio implementation.
 */
interface FakeSource {
  buffer: AudioBuffer | null
  onended: (() => void) | null
  startedAt: number
  connect: () => void
  disconnect: () => void
  start: (when: number) => void
  stop: () => void
}

function installFakeAudioContext() {
  const starts: number[] = []
  const clock = { t: 0 }

  const fake = {
    get currentTime() {
      return clock.t
    },
    state: 'running',
    sampleRate: 24_000,
    destination: {},
    createGain() {
      return {
        gain: { value: 1 },
        connect() {},
        disconnect() {},
      }
    },
    createBuffer(_channels: number, length: number, rate: number) {
      return {
        length,
        duration: length / rate,
        sampleRate: rate,
        getChannelData: () => new Float32Array(length),
      } as unknown as AudioBuffer
    },
    createBufferSource(): FakeSource {
      const node: FakeSource = {
        buffer: null,
        onended: null,
        startedAt: 0,
        connect() {},
        disconnect() {},
        start(when: number) {
          node.startedAt = when
          starts.push(when)
        },
        stop() {},
      }
      return node
    },
    async resume() {
      fake.state = 'running'
    },
    async close() {
      fake.state = 'closed'
    },
  }

  const Ctor = function AudioContext() {
    return fake
  } as unknown as typeof AudioContext
  const previous = globalThis.AudioContext
  globalThis.AudioContext = Ctor

  return {
    starts,
    advance(deltaSec: number) {
      clock.t += deltaSec
    },
    restore() {
      globalThis.AudioContext = previous
    },
  }
}

/** 100 ms of PCM16 mono @ 24 kHz (4800 bytes). */
function pcmFrame100ms(): ArrayBuffer {
  return new ArrayBuffer(4_800)
}

describe('PcmStreamPlayer', () => {
  let harness: ReturnType<typeof installFakeAudioContext>

  beforeEach(() => {
    harness = installFakeAudioContext()
  })

  afterEach(() => {
    harness.restore()
  })

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

  it('schedules consecutive chunks contiguously (gapless)', async () => {
    const player = new PcmStreamPlayer()
    // First frame: cursor 0 <= now 0 → re-anchor to 0.07, then += 0.1 → 0.17.
    player.enqueue(pcmFrame100ms())
    // Second frame, still at now=0: cursor 0.17 > now → start exactly at 0.17.
    player.enqueue(pcmFrame100ms())
    await Promise.resolve()
    await Promise.resolve()

    expect(harness.starts).toEqual([0.07, 0.17])
    player.stop()
  })

  it('does not re-anchor when the cursor sits inside the lead window', async () => {
    const player = new PcmStreamPlayer()
    player.enqueue(pcmFrame100ms())
    await Promise.resolve()
    await Promise.resolve()
    expect(harness.starts).toEqual([0.07])

    // Advance the clock so the cursor (0.17) is only 50 ms ahead of now —
    // inside the 70 ms lead window. The old code re-anchored to now+0.07
    // (0.19), opening a 20 ms gap from the previous slice's end (0.17).
    harness.advance(0.12)
    player.enqueue(pcmFrame100ms())
    await Promise.resolve()
    await Promise.resolve()

    // New behaviour: keep the cursor, start at 0.17 — flush with the first slice.
    expect(harness.starts[1]).toBeCloseTo(0.17, 6)
    player.stop()
  })

  it('re-anchors with lead after an underrun (cursor fell behind real time)', async () => {
    const player = new PcmStreamPlayer()
    player.enqueue(pcmFrame100ms())
    await Promise.resolve()
    await Promise.resolve()
    // First chunk scheduled at 0.07, cursor now 0.17.
    expect(harness.starts).toEqual([0.07])

    // Jump the clock past the scheduled tail → cursor 0.17 is in the past.
    harness.advance(1.0)
    player.enqueue(pcmFrame100ms())
    await Promise.resolve()
    await Promise.resolve()

    // Recovery: re-anchor to now (1.0) + lead (0.07).
    expect(harness.starts[1]).toBeCloseTo(1.07, 6)
    player.stop()
  })
})
