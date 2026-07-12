/** PCM16 mono source rate (OpenAI TTS streams at 24 kHz). */
const PLAYBACK_RATE = 24_000
/** ~150 ms of PCM16 mono @ 24 kHz — fewer tiny buffers, smoother on weak phones. */
const COALESCE_BYTES_DEFAULT = 7_200
/** ~250 ms coalesce on low-core devices. */
const COALESCE_BYTES_LOW_POWER = 12_000
/** Prebuffer before first scheduled chunk — absorbs WebSocket jitter so weak
 *  WebViews don't underrun on the first syllable. */
const PREBUFFER_BYTES_DEFAULT = 9_600
const PREBUFFER_BYTES_LOW_POWER = 16_800
/** Jitter buffer lead before each scheduled chunk (mobile WebViews stutter
 *  without it). Larger than before to hide main-thread GC pauses. */
const SCHEDULE_LEAD_SEC = 0.12
/** Lowpass cutoff for 24 kHz content — removes resampling aliasing and hiss
 *  above the source Nyquist (~12 kHz). */
const LOWPASS_HZ = 11_000

function isLowPowerDevice(): boolean {
  return (navigator.hardwareConcurrency || 8) <= 4
}

function int16ToFloat(sample: number): number {
  return sample / 32_768
}

export class PcmStreamPlayer {
  private context: AudioContext | null = null
  private gain: GainNode | null = null
  private lowpass: BiquadFilterNode | null = null
  private scheduledUntil = 0
  private pending = new Uint8Array(0)
  private activeSources = new Set<AudioBufferSourceNode>()
  private readonly coalesceBytes: number
  private readonly prebufferBytes: number
  private readonly onIdle: (() => void) | undefined
  /** Guards re-entrancy while drainPending awaits AudioContext.resume(). */
  private draining = false
  /** Set when flush() is requested during an in-flight drain. */
  private flushQueued = false
  /** False until we have enough bytes to start; reset on stop(). */
  private started = false

  constructor(onIdle?: () => void) {
    this.onIdle = onIdle
    const lowPower = isLowPowerDevice()
    this.coalesceBytes = lowPower ? COALESCE_BYTES_LOW_POWER : COALESCE_BYTES_DEFAULT
    this.prebufferBytes = lowPower ? PREBUFFER_BYTES_LOW_POWER : PREBUFFER_BYTES_DEFAULT
  }

  private async ensureContext(): Promise<AudioContext> {
    if (!this.context || this.context.state === 'closed') {
      // Use the device's native sample rate — forcing 24 kHz is unreliable on
      // many mobile WebViews and produces hiss/double-resampling. Buffers are
      // authored at PLAYBACK_RATE; the browser resamples to the output rate.
      this.context = new AudioContext({ latencyHint: 'playback' })
      this.lowpass = this.context.createBiquadFilter()
      this.lowpass.type = 'lowpass'
      this.lowpass.frequency.value = LOWPASS_HZ
      this.lowpass.Q.value = 0.7
      this.gain = this.context.createGain()
      this.gain.gain.value = 0.9
      this.lowpass.connect(this.gain)
      this.gain.connect(this.context.destination)
      this.scheduledUntil = 0
      this.started = false
    }
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }
    return this.context
  }

  /**
   * Create/resume the playback AudioContext inside a user gesture.
   * Telegram / iOS WebViews keep a late-created context suspended → silent TTS.
   */
  async unlock(): Promise<void> {
    await this.ensureContext()
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
    this.started = false
  }

  /**
   * Drain pending bytes into the scheduler.
   *
   * Scheduling is serialized: we await AudioContext readiness exactly once,
   * then schedule every coalesced slice synchronously. This keeps reads/writes
   * of `scheduledUntil` strictly ordered — concurrent enqueue() calls during
   * the await just append to `pending` and are picked up by the same loop
   * instead of launching racing schedulePcm() tasks.
   *
   * Before the first chunk we wait for `prebufferBytes` (or a flush) so that
   * network jitter doesn't cause an immediate underrun on slow devices.
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
      const lowpass = this.lowpass
      if (!gain || !lowpass) return

      while (true) {
        const wantFlush = flushAll || this.flushQueued
        const evenLength = this.pending.length - (this.pending.length % 2)
        if (evenLength < 2) break

        // Hold off scheduling until we have a comfortable prebuffer (unless
        // the stream ended — then play whatever we have).
        if (!this.started && !wantFlush && evenLength < this.prebufferBytes) break

        const take = wantFlush
          ? evenLength
          : evenLength >= this.coalesceBytes
            ? this.coalesceBytes
            : this.started
              ? evenLength
              : this.prebufferBytes
        if (take < 2) break

        const slice = this.pending.slice(0, take)
        this.pending = this.pending.slice(take)
        this.started = true
        this.schedulePcmSync(
          context,
          lowpass,
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
    lowpass: BiquadFilterNode,
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
    source.connect(lowpass)

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
