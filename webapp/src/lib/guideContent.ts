/** In-app onboarding + animated tips for the BeachOps Mini App. */

export interface GuideStep {
  id: string
  eyebrow: string
  title: string
  body: string
  accent?: string
}

export interface GuideTip {
  id: string
  topic: string
  title: string
  body: string
}

export const ONBOARDING_STEPS: GuideStep[] = [
  {
    id: 'welcome',
    eyebrow: 'BeachOps',
    title: 'Пульт ваших Cursor-агентов',
    body: 'Голос, Cloud и Windows, очередь и решения — в одном экране. Дальше коротко, как этим пользоваться.',
    accent: 'Старт',
  },
  {
    id: 'modes',
    eyebrow: 'Режимы',
    title: 'Спросить · спланировать · сделать',
    body: 'В Telegram: /ask без правок, /plan и /task с approve, /do сразу в базовую ветку. Здесь — эфир и контроль.',
    accent: 'Ask / Plan / Do',
  },
  {
    id: 'planes',
    eyebrow: 'Плоскости',
    title: 'Cloud рядом с Windows',
    body: 'Метрики сверху фильтруют срез. Windows-воркер на ПК claim’ит локальные jobs — чип внизу покажет online.',
    accent: 'Cloud · Windows',
  },
  {
    id: 'flow',
    eyebrow: 'Поток',
    title: 'Репо → задача → решение',
    body: 'Вкладка Репо — URL и ветка. Актив и Лента — очередь. Решения — approve плана. Голос не снимает panic и не approve’ит.',
    accent: 'Репо · Очередь · Owner',
  },
]

export const GUIDE_TIPS: GuideTip[] = [
  {
    id: 'repo-first',
    topic: 'Старт',
    title: 'Сначала репозиторий',
    body: 'Без активного репо промпт не уйдёт. Добавьте HTTPS GitHub URL во вкладке Репо или через /repo add в боте.',
  },
  {
    id: 'voice-plan',
    topic: 'Голос',
    title: 'Голос идёт в plan-first',
    body: 'Realtime-транскрипт и composer на вкладке Голос. Approve, panic и unpanic — только руками owner’а.',
  },
  {
    id: 'filter-metrics',
    topic: 'Пульт',
    title: 'Жмите метрики',
    body: 'Cloud / Очередь / Windows / В работе — это фильтры. Откроют нужный срез Актива без лишних табов.',
  },
  {
    id: 'windows-worker',
    topic: 'Windows',
    title: 'Локальный агент на ПК',
    body: 'Установите worker: .\\scripts\\install-windows-worker.ps1. Слоту нужны runtime=windows и local_path к репо.',
  },
  {
    id: 'slots',
    topic: 'Агенты',
    title: 'Несколько сессий',
    body: 'В боте /agents и /new — до 8 слотов. Каждый помнит репо и историю Cursor. Модель меняется здесь, на Пульте.',
  },
  {
    id: 'approvals',
    topic: 'Безопасность',
    title: 'План ждёт owner',
    body: 'После /plan или /task кнопки Approve одноразовые и с TTL. Вкладка Решения — то же в Mini App.',
  },
  {
    id: 'queue',
    topic: 'Очередь',
    title: 'Сообщения не теряются',
    body: 'Пока агент занят, новые задачи копятся в durable-очереди. /cancel в боте снимает run и хвост.',
  },
  {
    id: 'passkey',
    topic: 'Доступ',
    title: 'Passkey для браузера',
    body: 'Owner: откройте /dashboard в Telegram и нажмите отпечаток. Потом вход с Face ID / Windows Hello без Telegram.',
  },
  {
    id: 'self-deploy',
    topic: 'Деплой',
    title: 'Свой инстанс',
    body: 'Скопируйте .env.example → .env и docker compose up -d --build. CI self-deploy автора — отдельный поток с owner approve.',
  },
  {
    id: 'self-improve',
    topic: 'Self-improve',
    title: 'Бот правит себя — opt-in',
    body: 'SELF_IMPROVE_ENABLED=1 и кнопка на вкладке Репо. Write только в feature-branch; main защищён.',
  },
]

export const TIP_TOPICS = [
  'Все',
  ...Array.from(new Set(GUIDE_TIPS.map((tip) => tip.topic))),
]
