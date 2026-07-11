/** Mini App tips — how to use this screen, not Telegram slash commands. */

export interface TipItem {
  id: string
  title: string
  hint: string
  copy: string
}

export const FLOW_TIPS: TipItem[] = [
  {
    id: 'voice',
    title: 'Голос',
    hint: 'Вкладка «Голос»',
    copy: 'Коснись орба и говори — сразу в работу. Текст рядом, если удобнее набрать.',
  },
  {
    id: 'ask',
    title: 'Спросить',
    hint: 'Без правок в коде',
    copy: 'Короткий вопрос агенту. Репозиторий только читает.',
  },
  {
    id: 'plan',
    title: 'План',
    hint: 'Сначала разбор',
    copy: 'Агент исследует и сразу продолжает выполнение (auto-approve). Без ручного approve.',
  },
  {
    id: 'do',
    title: 'Сделать',
    hint: 'Сразу в ветку',
    copy: 'Пишет в активную базовую ветку. Нужна роль оператора или владельца.',
  },
]

export const PLACE_TIPS: TipItem[] = [
  {
    id: 'runtime',
    title: 'Cloud / Windows',
    hint: 'Панель управления',
    copy: 'Cloud — в облаке Cursor. Windows — на вашем ПК, нужен путь к репо и онлайн-воркер.',
  },
  {
    id: 'ether',
    title: 'Эфир задачи',
    hint: 'Под диалогом',
    copy: 'Живой ход агента. Тап по задаче в «Актив» — переключает эфир.',
  },
  {
    id: 'repos',
    title: 'Репо',
    hint: 'Вкладка «Репо»',
    copy: 'Открытый режим — любой GitHub URL. Строгий — нажмите репо из списка. Активный = куда уходят задачи.',
  },
  {
    id: 'approvals',
    title: 'Пульт',
    hint: 'Очередь и режим',
    copy: 'Статус задач и переключатель «Самосовершенствование» — вкл/выкл одной кнопкой.',
  },
]
