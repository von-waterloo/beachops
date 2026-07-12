const PLAYBACK_RATE = 24_000
/** ~100 ms of PCM16 mono @ 24 kHz — fewer tiny buffers on weak phones. */
const COALESCE_BYTES_DEFAULT = 4_800
/** ~200 ms coalesce on low-core devices. */
const COALESCE_BYTES_LOW_POWER = 9_600
/** Jitter buffer before first scheduled chunk (mobile WebViews stutter without it). */
const SCHEDULE_LEAD_SEC = 0.07

function isLowPowerDevice(): boolean {
  return (navigator.hardwareConcurrency || 8) <= 4
}

function int16ToFloat(sample: number): number {
  return sample / 32_768
}

export class PcmStreamPlayer {
  private context: AudioContext | null = null
  private gain: GainNode | null = null
  private scheduledUntil = 0
  private pending = new Uint8Array(0)
  private activeSources = new Set<AudioBufferSourceNode>()
  private readonly coalesceBytes: number
  private readonly onIdle: (() => void) | undefined
  /** Guards re-entrancy while drainPending awaits AudioContext.resume(). */
  private draining = false
  /** Set when flush() is requested during an in-flight drain. */
  private flushQueued = false

  constructor(onIdle?: () => void) {
    this.onIdle = onIdle
    this.coalesceBytes = isLowPowerDevice()
      ? COALESCE_BYTES_LOW_POWER
      : COALESCE_BYTES_DEFAULT
  }

  private async ensureContext(): Promise<AudioContext> {
    if (!this.context || this.context.state === 'closed') {
      this.context = new AudioContext({
        sampleRate: PLAYBACK_RATE,
        latencyHint: 'playback',
      })
      this.gain = this.context.createGain()
      this.gain.gain.value = 0.9
      this.gain.connect(this.context.destination)
      this.scheduledUntil = 0
    }
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }
    return this.context
  }

  enqueue(chunk: ArrayBuffer): void {
    if (!chunk.byteLength) return
    const merged = new Uint8Array(this.pending.length + chunk.byteLength)
    merged.set(this.pending, 0)
    merged.set(new Uint8Array(chunk), this.pending.length)
    this.pending = merged
    void this.drainPending(false)
  }

  /** Play tail after server signals end of stream. */
  flush(): void {
    void this.drainPending(true)
  }

  stop(): void {
    for (const source of this.activeSources) {
      try {
        source.stop()
      } catch {
        // already stopped
      }
      source.disconnect()
    }
    this.activeSources.clear()
    this.pending = new Uint8Array(0)
    this.scheduledUntil = 0
    this.draining = false
    this.flushQueued = false
  }

  /**
   * Drain pending bytes into the scheduler.
   *
   * Scheduling is serialized: we await AudioContext readiness exactly once,
   * then schedule every coalesced slice synchronously. This keeps reads/writes
   * of `scheduledUntil` strictly ordered — concurrent enqueue() calls during
   * the await just append to `pending` and are picked up by the same loop
   * instead of launching racing schedulePcm() tasks.
   */
  private async drainPending(flushAll: boolean): Promise<void> {
    if (this.draining) {
      if (flushAll) this.flushQueued = true
      return
    }
    this.draining = true
    try {
      const context = await this.ensureContext()
      // stop() may have closed the context while we were resuming.
      if (context.state === 'closed') return
      const gain = this.gain
      if (!gain) return

      while (true) {
        const wantFlush = flushAll || this.flushQueued
        const evenLength = this.pending.length - (this.pending.length % 2)
        if (evenLength < 2) break

        const take = wantFlush
          ? evenLength
          : evenLength >= this.coalesceBytes
            ? this.coalesceBytes
            : 0
        if (take < 2) break

        const slice = this.pending.slice(0, take)
        this.pending = this.pending.slice(take)
        this.schedulePcmSync(
          context,
          gain,
          slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.byteLength),
        )
      }
      this.flushQueued = false
    } finally {
      this.draining = false
    }
  }

  private schedulePcmSync(
    context: AudioContext,
    gain: GainNode,
    raw: ArrayBuffer,
  ): void {
    if (raw.byteLength < 2) return

    const pcm = new Int16Array(raw)
    const buffer = context.createBuffer(1, pcm.length, PLAYBACK_RATE)
    const channel = buffer.getChannelData(0)
    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = int16ToFloat(pcm[index]!)
    }

    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(gain)

    const now = context.currentTime
    // Only re-anchor when the cursor is not strictly ahead of real time (first
    // chunk, or underrun after a network stall). Re-anchoring while already
    // scheduled ahead — even inside the lead window — would push the next slice
    // forward and open a gap between it and the previous slice.
    if (this.scheduledUntil <= now) {
      this.scheduledUntil = now + SCHEDULE_LEAD_SEC
    }
    source.start(this.scheduledUntil)
    this.scheduledUntil += buffer.duration

    this.activeSources.add(source)
    source.onended = () => {
      source.disconnect()
      this.activeSources.delete(source)
      if (
        this.activeSources.size === 0
        && this.pending.length === 0
        && !this.draining
      ) {
        this.onIdle?.()
      }
    }
  }
}
