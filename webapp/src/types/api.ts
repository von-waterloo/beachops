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
}

export interface Event {
  id: string
  kind: string
  summary: string
  createdAt: string
  jobId?: string
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

export interface JobStreamEvent {
  id: string
  eventType: string
  text: string | null
  createdAt: string | null
}

export interface JobStreamSnapshot {
  jobId: string
  status: string
  events: JobStreamEvent[]
  lastEventId: string
  latestText: string | null
  finalText: string | null
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
  usage: Usage | null
  role: string
  defaultBranch?: string
  repositoryPolicy?: RepositoryPolicyInfo
  workers: WorkerNode[]
  queue: QueueSnapshot
  selfImprove?: SelfImproveInfo
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
