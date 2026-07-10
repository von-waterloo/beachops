class BeachOpsPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = []
    this.targetRate = 24000
    this.ratio = sampleRate / this.targetRate
    this.position = 0
  }

  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel?.length) return true

    const output = []
    let position = this.position
    while (position < channel.length) {
      const left = Math.floor(position)
      const right = Math.min(channel.length - 1, left + 1)
      const fraction = position - left
      const sample = channel[left] * (1 - fraction) + channel[right] * fraction
      output.push(Math.max(-1, Math.min(1, sample)))
      position += this.ratio
    }
    this.position = position - channel.length

    if (output.length) {
      const pcm = new Int16Array(output.length)
      for (let index = 0; index < output.length; index += 1) {
        const sample = output[index]
        pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer])
    }
    return true
  }
}

registerProcessor('beachops-pcm', BeachOpsPcmProcessor)
