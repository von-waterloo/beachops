export type JobStatus =
  | 'draft'
  | 'queued'
  | 'planning'
  | 'awaiting_approval'
  | 'approved'
  | 'running'
  | 'review_required'
  | 'revision_requested'
  | 'paused'
  | 'blocked'
  | 'completed'
  | 'succeeded'
  | 'accepted'
  | 'rejected'
  | 'cancelled'
  | 'failed'

export interface Job {
  id: string
  title: string
  status: JobStatus
  createdAt: string
  progress?: number
  repository?: string
  runtime?: string
  workerNodeId?: string | null
  cursorAgentId?: string | null
  cursorUrl?: string | null
  branch?: string | null
  totalTokens?: number | null
  inputTokens?: number | null
  outputTokens?: number | null
  cacheReadTokens?: number | null
  cacheWriteTokens?: number | null
}

export interface Event {
  id: string
  kind: string
  summary: string
  createdAt: string
  jobId?: string
  toStatus?: string | null
  title?: string | null
  repository?: string | null
  runtime?: string | null
  branch?: string | null
}

export interface Approval {
  id: string
  title: string
  risk: 'low' | 'medium' | 'high'
  requestedAt: string
  repository?: string
}

export interface Repository {
  id: string
  name: string
  url?: string
  branch: string
  status: 'ready' | 'busy' | 'offline'
  active?: boolean
  selfImprove?: boolean
  lastActivityAt?: string
}

export interface AgentSlot {
  id: string
  label: string
  runtime?: string
  active?: boolean
  repository?: string | null
  localPath?: string | null
  preferredWorkerId?: string | null
  cursorAgentId?: string | null
  cursorUrl?: string | null
}

export interface StreamEvent {
  id: string
  eventType: string
  text: string | null
  createdAt: string
}

export interface Usage {
  period: string
  voiceMinutes: number
  jobs: number
  limitPercent: number
  totalTokens?: number
}

export interface WorkerNode {
  id: string
  hostname: string
  platform: string
  status: string
  lastHeartbeatAt?: string | null
  capabilities?: Record<string, unknown>
}

export interface JobStreamSnapshot {
  jobId: string
  status: JobStatus | string
  events: StreamEvent[]
  lastEventId: string
  latestText: string | null
  finalText: string | null
}

export interface QueueSnapshot {
  pending: number
  running: number
  active: number
  queued: number
  blocked: number
  total?: number
}

export interface SelfImproveInfo {
  enabled: boolean
  repoUrl?: string | null
  branches: string[]
  canToggle?: boolean
  needsRepo?: boolean
}

export interface AllowedRepository {
  url: string
  branches: string[]
}

export interface RepositoryPolicyInfo {
  openMode: boolean
  repositories: AllowedRepository[]
}

export interface DashboardSnapshot {
  jobs: Job[]
  events: Event[]
  approvals: Approval[]
  repositories: Repository[]
  agents: AgentSlot[]
  panic?: boolean
  usage: Usage | null
  role: string
  defaultBranch?: string
  repositoryPolicy?: RepositoryPolicyInfo
  workers: WorkerNode[]
  queue: QueueSnapshot
  selfImprove?: SelfImproveInfo | null
}

export function isActiveJobStatus(status: JobStatus): boolean {
  return [
    'queued',
    'planning',
    'approved',
    'running',
    'awaiting_approval',
    'review_required',
    'revision_requested',
    'paused',
    'blocked',
  ].includes(status)
}
