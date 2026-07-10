/** Capability map for Mini App «Пульт» — mirrors Telegram bot surface. */

export interface CapabilityItem {
  id: string
  title: string
  command: string
  copy: string
}

export const MODE_CAPABILITIES: CapabilityItem[] = [
  {
    id: 'ask',
    title: 'Чат',
    command: '/ask',
    copy: 'Ответ по коду без правок. Голос и текст в том же режиме.',
  },
  {
    id: 'plan',
    title: 'План',
    command: '/plan · /task',
    copy: 'Исследование → сюда же попадёт approve владельца.',
  },
  {
    id: 'do',
    title: 'Действие',
    command: '/do',
    copy: 'Сразу пишет в базовую ветку (dev). main/master → ветка + PR.',
  },
]

export const OPS_CAPABILITIES: CapabilityItem[] = [
  {
    id: 'agents',
    title: 'Агенты',
    command: '/agents · /new',
    copy: 'Несколько слотов Cursor: Cloud и Windows, переключение без потери истории.',
  },
  {
    id: 'repo',
    title: 'Репозитории',
    command: '/repo',
    copy: 'Добавить GitHub URL, выбрать активный, задать базовую ветку.',
  },
  {
    id: 'memory',
    title: 'Память',
    command: '/remember · /memory',
    copy: 'Заметки и семантический поиск по активному репо; runs пишутся сами.',
  },
  {
    id: 'jobs',
    title: 'Очередь',
    command: '/jobs · /cancel',
    copy: 'Durable очередь, статусы, отмена активного run.',
  },
]

export const OWNER_CAPABILITIES: CapabilityItem[] = [
  {
    id: 'approvals',
    title: 'Approve',
    command: '/approvals',
    copy: 'Только после /plan или /task. Голос сам не одобрит высокий риск.',
  },
  {
    id: 'panic',
    title: 'Panic',
    command: '/panic · /unpanic',
    copy: 'Аварийно режет write-действия по всем репо.',
  },
  {
    id: 'rollback',
    title: 'Откат',
    command: '/rollback',
    copy: 'Вернуть прод на предыдущий SHA — с кнопкой подтверждения.',
  },
]

export function selfImproveCopy(enabled: boolean, branches: string[]): CapabilityItem {
  return {
    id: 'self-improve',
    title: 'Самосовершенствование',
    command: enabled ? 'включено' : 'выкл. в .env',
    copy: enabled
      ? `Бот может править свой BeachOps-форк (${branches.join(', ') || 'dev'}). Деплой — только owner approve / Actions, не сам.`
      : 'Opt-in: SELF_IMPROVE_ENABLED + URL форка. По умолчанию выключено.',
  }
}
