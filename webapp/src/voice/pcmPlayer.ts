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
    this.drainPending(false)
  }

  /** Play tail after server signals end of stream. */
  flush(): void {
    this.drainPending(true)
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
  }

  private drainPending(flushAll: boolean): void {
    while (true) {
      const evenLength = this.pending.length - (this.pending.length % 2)
      if (evenLength < 2) break

      const take = flushAll
        ? evenLength
        : evenLength >= this.coalesceBytes
          ? this.coalesceBytes
          : 0
      if (take < 2) break

      const slice = this.pending.slice(0, take)
      this.pending = this.pending.slice(take)
      void this.schedulePcm(
        slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.byteLength),
      )
    }
  }

  private async schedulePcm(raw: ArrayBuffer): Promise<void> {
    const context = await this.ensureContext()
    const gain = this.gain
    if (!gain || raw.byteLength < 2) return

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
    if (this.scheduledUntil < now + SCHEDULE_LEAD_SEC) {
      this.scheduledUntil = now + SCHEDULE_LEAD_SEC
    }
    source.start(this.scheduledUntil)
    this.scheduledUntil += buffer.duration

    this.activeSources.add(source)
    source.onended = () => {
      source.disconnect()
      this.activeSources.delete(source)
      if (this.activeSources.size === 0 && this.pending.length === 0) {
        this.onIdle?.()
      }
    }
  }
}
