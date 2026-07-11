/** GitHub OAuth helpers for pinning repositories. */

import { apiFetch, apiUrl } from './api'

export interface GithubConnectionStatus {
  configured: boolean
  connected: boolean
  login: string | null
}

export interface GithubRemoteRepo {
  url: string
  fullName: string
  private: boolean
  defaultBranch: string
}

export async function fetchGithubStatus(): Promise<GithubConnectionStatus> {
  return apiFetch<GithubConnectionStatus>('/api/auth/github/status')
}

export function githubOAuthStartUrl(): string {
  return apiUrl('/api/auth/github/start')
}

export async function disconnectGithub(): Promise<void> {
  await apiFetch('/api/auth/github', { method: 'DELETE' })
}

export async function fetchGithubRepos(page = 1): Promise<GithubRemoteRepo[]> {
  const result = await apiFetch<{ repositories: GithubRemoteRepo[] }>(
    `/api/github/repos?page=${page}`,
  )
  return result.repositories ?? []
}

/** Prefer a non-protected base branch when GitHub default is main/master. */
export function pinBranchFor(repo: GithubRemoteRepo): string {
  const branch = (repo.defaultBranch || 'dev').trim()
  if (branch.toLowerCase() === 'main' || branch.toLowerCase() === 'master') {
    return 'dev'
  }
  return branch || 'dev'
}
