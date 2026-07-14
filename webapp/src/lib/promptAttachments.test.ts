import { describe, expect, it } from 'vitest'
import {
  collectAttachments,
  isAcceptedImageFile,
  MAX_ATTACHMENTS,
} from './promptAttachments'

function fakeFile(name: string, size: number, type: string): File {
  const blob = new Blob([new Uint8Array(size)], { type })
  return new File([blob], name, { type })
}

describe('promptAttachments', () => {
  it('accepts common image files and rejects svg', () => {
    expect(isAcceptedImageFile(fakeFile('a.png', 10, 'image/png'))).toBe(true)
    expect(isAcceptedImageFile(fakeFile('a.svg', 10, 'image/svg+xml'))).toBe(false)
  })

  it('keeps successful files when one file in the batch fails', async () => {
    const ok = fakeFile('ok.png', 32, 'image/png')
    const bad = fakeFile('bad.svg', 32, 'image/svg+xml')
    const { next, error } = await collectAttachments([ok, bad], [])
    expect(next).toHaveLength(1)
    expect(next[0]?.mimeType).toBe('image/png')
    expect(error).toMatch(/PNG|JPEG|WebP|GIF/i)
  })

  it('returns a clear error when already at max', async () => {
    const current = Array.from({ length: MAX_ATTACHMENTS }, (_, index) => ({
      id: String(index),
      mimeType: 'image/png',
      previewUrl: 'data:image/png;base64,aa',
      dataUrl: 'data:image/png;base64,aa',
      byteSize: 10,
    }))
    const { next, error } = await collectAttachments(
      [fakeFile('extra.png', 10, 'image/png')],
      current,
    )
    expect(next).toHaveLength(MAX_ATTACHMENTS)
    expect(error).toMatch(/Максимум/)
  })
})
