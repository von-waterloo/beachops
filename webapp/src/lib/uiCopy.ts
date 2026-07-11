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
  return runtime === 'windows' ? 'Windows' : 'Cloud'
}

const EVENT_TYPE_RU: Record<string, string> = {
  'run.progress': 'Прогресс',
  'run.finished': 'Готово',
  'run.failed': 'Сбой',
  'worker.started': 'Старт',
  'worker.claimed': 'Воркер взял',
  'worker.finished': 'Воркер завершил',
  'worker.observation_done': 'Наблюдение',
  'approval.requested': 'Ждёт approve',
}

export function eventTypeLabel(eventType: string): string {
  return EVENT_TYPE_RU[eventType] ?? eventType
}
