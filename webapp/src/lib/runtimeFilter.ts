export type RuntimeFilter = 'all' | 'cloud' | 'windows'

export function matchesRuntimeFilter(
  runtime: string | null | undefined,
  filter: RuntimeFilter,
): boolean {
  if (filter === 'all') return true
  if (filter === 'windows') return runtime === 'windows'
  return runtime !== 'windows'
}

export const RUNTIME_FILTER_LABELS: Record<RuntimeFilter, string> = {
  all: 'Все',
  cloud: 'Cloud',
  windows: 'Windows',
}
