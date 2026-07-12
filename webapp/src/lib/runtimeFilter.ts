export type RuntimeFilter = 'all' | 'cloud' | 'windows'

/** Cloud-only product: windows filter is treated as cloud. */
export function matchesRuntimeFilter(
  runtime: string | null | undefined,
  filter: RuntimeFilter,
): boolean {
  if (filter === 'all') return true
  // Never surface windows as a separate plane.
  if (filter === 'windows') return false
  return runtime !== 'windows'
}

export const RUNTIME_FILTER_LABELS: Record<RuntimeFilter, string> = {
  all: 'Все',
  cloud: 'Cloud',
  windows: 'Cloud',
}
