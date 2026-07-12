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
    sampleRate: 48_000,
    destination: {},
    createGain() {
      return {
        gain: { value: 1 },
        connect() {},
        disconnect() {},
      }
    },
    createBiquadFilter() {
      return {
        type: 'lowpass',
        frequency: { value: 11_000 },
        Q: { value: 0.7 },
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

/** 150 ms of PCM16 mono @ 24 kHz (7200 bytes = 3600 samples). */
function pcmFrame150ms(): ArrayBuffer {
  return new ArrayBuffer(7_200)
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

  it('unlock creates a running AudioContext under a user gesture', async () => {
    const player = new PcmStreamPlayer()
    await player.unlock()
    expect(harness.starts).toEqual([])
    player.stop()
  })

  it('stop clears pending without touching AudioContext', () => {
    const player = new PcmStreamPlayer()
    player.enqueue(new Uint8Array([0, 0, 1, 2]).buffer)
    expect(() => player.stop()).not.toThrow()
  })

  it('prebuffers until enough bytes arrive, then schedules', async () => {
    const player = new PcmStreamPlayer()
    // A single 150 ms frame is below the prebuffer threshold on every device →
    // nothing scheduled yet.
    player.enqueue(pcmFrame150ms())
    await Promise.resolve()
    await Promise.resolve()
    expect(harness.starts).toEqual([])

    // Feed enough to cross the largest (low-power) prebuffer threshold too, so
    // the assertion is deterministic across CI runners and local machines.
    player.enqueue(pcmFrame150ms())
    player.enqueue(pcmFrame150ms())
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(harness.starts.length).toBeGreaterThanOrEqual(1)
    player.stop()
  })

  it('schedules consecutive chunks contiguously (gapless) on flush', async () => {
    const player = new PcmStreamPlayer()
    // Flush forces whatever is pending to play immediately (re-anchor to lead).
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()
    // First chunk: cursor 0 <= now 0 → re-anchor to 0.12, then += 0.15 → 0.27.
    expect(harness.starts).toEqual([0.12])

    // Second frame, still at now=0: cursor 0.27 > now → start exactly at 0.27.
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()
    expect(harness.starts).toEqual([0.12, 0.27])
    player.stop()
  })

  it('does not re-anchor when the cursor sits inside the lead window', async () => {
    const player = new PcmStreamPlayer()
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()
    expect(harness.starts).toEqual([0.12])

    // Advance the clock so the cursor (0.27) is right at the edge of the
    // 120 ms lead window. The old code re-anchored to now+lead, opening a gap.
    harness.advance(0.15)
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()

    // New behaviour: keep the cursor, start at 0.27 — flush with the first slice.
    expect(harness.starts[1]).toBeCloseTo(0.27, 6)
    player.stop()
  })

  it('re-anchors with lead after an underrun (cursor fell behind real time)', async () => {
    const player = new PcmStreamPlayer()
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()
    // First chunk scheduled at 0.12, cursor now 0.27.
    expect(harness.starts).toEqual([0.12])

    // Jump the clock past the scheduled tail → cursor 0.27 is in the past.
    harness.advance(1.0)
    player.enqueue(pcmFrame150ms())
    player.flush()
    await Promise.resolve()
    await Promise.resolve()

    // Recovery: re-anchor to now (1.0) + lead (0.12).
    expect(harness.starts[1]).toBeCloseTo(1.12, 6)
    player.stop()
  })
})
