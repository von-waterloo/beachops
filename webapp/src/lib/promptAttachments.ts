/** Shared image attachment helpers for voice composer and agent prompt UI. */

export const MAX_ATTACHMENTS = 5
export const MAX_IMAGE_BYTES = 4 * 1024 * 1024
export const ACCEPTED_MIME = new Set([
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/webp',
  'image/gif',
])

export interface PromptAttachment {
  id: string
  mimeType: string
  previewUrl: string
  dataUrl: string
}

export function normalizeMime(mime: string): string {
  const value = mime.trim().toLowerCase()
  if (value === 'image/jpg') return 'image/jpeg'
  return value
}

export async function fileToAttachment(file: File): Promise<PromptAttachment> {
  const mimeType = normalizeMime(file.type || 'image/png')
  if (!ACCEPTED_MIME.has(mimeType)) {
    throw new Error('Нужен PNG, JPEG, WebP или GIF')
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new Error('Картинка больше 4 МБ')
  }
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Не удалось прочитать файл'))
    reader.readAsDataURL(file)
  })
  return {
    id: crypto.randomUUID(),
    mimeType,
    previewUrl: dataUrl,
    dataUrl,
  }
}

export function attachmentPayload(items: PromptAttachment[]): Array<{ mimeType: string; data: string }> {
  return items.map((item) => ({
    mimeType: item.mimeType,
    data: item.dataUrl,
  }))
}

export async function collectAttachments(
  files: FileList | File[],
  current: PromptAttachment[],
): Promise<{ next: PromptAttachment[]; error: string | null }> {
  const list = Array.from(files)
  if (!list.length) return { next: current, error: null }
  const room = MAX_ATTACHMENTS - current.length
  if (room <= 0) {
    return { next: current, error: `Максимум ${MAX_ATTACHMENTS} скринов за раз` }
  }
  const added = await Promise.all(list.slice(0, room).map((file) => fileToAttachment(file)))
  return {
    next: [...current, ...added].slice(0, MAX_ATTACHMENTS),
    error: null,
  }
}
