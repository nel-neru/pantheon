import { describe, expect, it } from 'vitest'

import { levelBadge, priorityBadge, priorityLabel, statusBadge, statusLabel } from '../labels'

describe('labels', () => {
  it('status を日本語化し未知値はそのまま返す', () => {
    expect(statusLabel('running')).toBe('実行中')
    expect(statusLabel('completed')).toBe('完了')
    expect(statusLabel('mystery')).toBe('mystery')
    expect(statusLabel(null)).toBe('—')
  })

  it('status バッジ色は完了=緑/失敗=赤/保留=黄で一貫する', () => {
    expect(statusBadge('completed')).toBe('badge-green')
    expect(statusBadge('failed')).toBe('badge-red')
    expect(statusBadge('pending')).toBe('badge-yellow')
    expect(statusBadge(undefined)).toBe('badge-neutral')
  })

  it('priority は high/critical=赤, medium=黄, low=neutral', () => {
    expect(priorityLabel('high')).toBe('高')
    expect(priorityBadge('critical')).toBe('badge-red')
    expect(priorityBadge('medium')).toBe('badge-yellow')
    expect(priorityBadge('low')).toBe('badge-neutral')
  })

  it('level バッジは error=赤, warning=黄, success=緑', () => {
    expect(levelBadge('error')).toBe('badge-red')
    expect(levelBadge('warning')).toBe('badge-yellow')
    expect(levelBadge('success')).toBe('badge-green')
  })
})
