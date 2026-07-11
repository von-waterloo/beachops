import { describe, expect, it } from 'vitest'
import { mergeAgentSlot } from './useDashboard'
import type { AgentSlot } from '../types/api'

const cloud: AgentSlot = {
  id: '1',
  label: 'Main',
  runtime: 'cloud',
  active: true,
  localPath: null,
}

describe('mergeAgentSlot', () => {
  it('applies windows runtime from PATCH onto the matching slot', () => {
    const updated: AgentSlot = {
      ...cloud,
      runtime: 'windows',
      localPath: 'D:\\Work\\AI-ContentMaker',
    }
    const next = mergeAgentSlot([cloud], '1', updated)
    expect(next[0]?.runtime).toBe('windows')
    expect(next[0]?.localPath).toBe('D:\\Work\\AI-ContentMaker')
  })

  it('deactivates other slots when makeActive is set', () => {
    const other: AgentSlot = { id: '2', label: 'Other', runtime: 'cloud', active: true }
    const updated: AgentSlot = { ...cloud, active: true }
    const next = mergeAgentSlot([cloud, other], '1', updated, true)
    expect(next.find((s) => s.id === '1')?.active).toBe(true)
    expect(next.find((s) => s.id === '2')?.active).toBe(false)
  })
})
