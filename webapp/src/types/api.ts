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
  branch: string
  status: 'ready' | 'busy' | 'offline'
  lastActivityAt?: string
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

export interface DashboardSnapshot {
  jobs: Job[]
  events: Event[]
  approvals: Approval[]
  repositories: Repository[]
  usage: Usage | null
  panic: boolean
  role: string
  workers: WorkerNode[]
  queue: QueueSnapshot
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
