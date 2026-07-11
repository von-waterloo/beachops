/** Russian UI copy and status labels for the BeachOps Mini App. */

const STATUS_RU: Record<string, string> = {
  queued: 'В очереди',
  planning: 'План',
  approved: 'Одобрено',
  running: 'В работе',
  awaiting_approval: 'Ждёт решения',
  review_required: 'На ревью',
  blocked: 'Блок',
  revision_requested: 'Доработка',
  completed: 'Готово',
  accepted: 'Принято',
  failed: 'Сбой',
  cancelled: 'Отмена',
  rejected: 'Отклонено',
  draft: 'Черновик',
  paused: 'Пауза',
  online: 'Онлайн',
  offline: 'Офлайн',
  ready: 'Готов',
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
}

const ROLE_RU: Record<string, string> = {
  owner: 'Владелец',
  operator: 'Оператор',
  viewer: 'Наблюдатель',
  admin: 'Владелец',
  none: 'Гость',
}

export function statusLabel(status: string): string {
  return STATUS_RU[status] ?? status
}

export function roleLabel(role: string): string {
  return ROLE_RU[role.toLowerCase()] ?? role
}

export function riskLabel(risk: string): string {
  const base = STATUS_RU[risk.toLowerCase()] ?? risk
  return `${base} риск`
}

export function relativeTimeRu(value?: string | null): string {
  if (!value) return 'Только что'
  const delta = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.floor(delta / 60_000)
  if (minutes < 1) return 'Сейчас'
  if (minutes < 60) return `${minutes} мин назад`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} ч назад`
  return `${Math.floor(minutes / 1440)} дн назад`
}

export function runtimeLabel(runtime?: string | null): string {
  void runtime
  return 'Cloud'
}

const EVENT_TYPE_RU: Record<string, string> = {
  'run.progress': 'Прогресс',
  'run.finished': 'Завершён',
  'run.failed': 'Сбой прогона',
  'worker.started': 'Воркер запустил',
  'worker.claimed': 'Воркер взял задачу',
  'worker.finished': 'Воркер завершил',
  'worker.failed': 'Воркер упал',
  'worker.observation_done': 'Наблюдение',
  'approval.requested': 'Запрошено решение',
  'approval.approved': 'Одобрено',
  'approval.rejected': 'Отклонено',
  'user.cancel': 'Отменено вами',
  'user.cancel_queued': 'Снято из очереди',
}

export function eventTypeLabel(eventType: string): string {
  return EVENT_TYPE_RU[eventType] ?? eventType
}

/** Tone for timeline dots / pills: success | danger | warn | active | muted */
export function statusTone(status?: string | null): string {
  const key = (status || '').toLowerCase()
  if (['completed', 'succeeded', 'accepted'].includes(key)) return 'success'
  if (['failed', 'rejected', 'cancelled'].includes(key)) return 'danger'
  if (
    ['awaiting_approval', 'review_required', 'blocked', 'revision_requested', 'paused'].includes(
      key,
    )
  ) {
    return 'warn'
  }
  if (['running', 'planning', 'queued', 'approved'].includes(key)) return 'active'
  return 'muted'
}

export function eventHeadline(event: {
  summary?: string
  toStatus?: string | null
  kind?: string
}): string {
  const status = event.toStatus || event.summary
  if (status && STATUS_RU[status]) return statusLabel(status)
  if (event.kind) return eventTypeLabel(event.kind)
  return event.summary || 'Событие'
}
