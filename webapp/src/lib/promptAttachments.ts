/** Shared image attachment helpers for voice composer and agent prompt UI. */

export const MAX_ATTACHMENTS = 5
export const MAX_IMAGE_BYTES = 4 * 1024 * 1024
export const MAX_IMAGES_TOTAL_BYTES = 12 * 1024 * 1024
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
  byteSize: number
}

export function normalizeMime(mime: string): string {
  const value = mime.trim().toLowerCase()
  if (value === 'image/jpg') return 'image/jpeg'
  return value
}

export function isAcceptedImageFile(file: File): boolean {
  const mime = normalizeMime(file.type || '')
  if (mime && ACCEPTED_MIME.has(mime)) return true
  // Some paste sources omit MIME — allow by extension.
  const name = file.name.toLowerCase()
  return /\.(png|jpe?g|webp|gif)$/.test(name)
}

export async function fileToAttachment(file: File): Promise<PromptAttachment> {
  const mimeType = normalizeMime(file.type || 'image/png')
  if (!ACCEPTED_MIME.has(mimeType) && !isAcceptedImageFile(file)) {
    throw new Error('Нужен PNG, JPEG, WebP или GIF')
  }
  const resolvedMime = ACCEPTED_MIME.has(mimeType) ? mimeType : 'image/png'
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
    mimeType: resolvedMime,
    previewUrl: dataUrl,
    dataUrl,
    byteSize: file.size,
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

  const selected = list.slice(0, room)
  const results = await Promise.allSettled(selected.map((file) => fileToAttachment(file)))
  const added: PromptAttachment[] = []
  const errors: string[] = []
  let totalBytes = current.reduce((sum, item) => sum + (item.byteSize || 0), 0)

  for (const result of results) {
    if (result.status === 'rejected') {
      errors.push(result.reason instanceof Error ? result.reason.message : 'Ошибка файла')
      continue
    }
    const item = result.value
    if (totalBytes + item.byteSize > MAX_IMAGES_TOTAL_BYTES) {
      errors.push('Суммарный размер скринов слишком большой')
      break
    }
    totalBytes += item.byteSize
    added.push(item)
  }

  if (!added.length) {
    return {
      next: current,
      error: errors[0] || `Максимум ${MAX_ATTACHMENTS} скринов за раз`,
    }
  }

  const truncated = list.length > room
  const warning = truncated
    ? `Добавлено ${added.length} из ${list.length} (лимит ${MAX_ATTACHMENTS})`
    : errors[0] || null

  return {
    next: [...current, ...added].slice(0, MAX_ATTACHMENTS),
    error: warning,
  }
}
