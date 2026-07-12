export type RuntimeFilter = 'all' | 'cloud'

/** Cloud-only: legacy `windows` jobs still pass through `all`. */
export function matchesRuntimeFilter(
  runtime: string | null | undefined,
  filter: RuntimeFilter,
): boolean {
  if (filter === 'all') return true
  return runtime !== 'windows'
}

export const RUNTIME_FILTER_LABELS: Record<RuntimeFilter, string> = {
  all: 'Все',
  cloud: 'Cloud',
}
