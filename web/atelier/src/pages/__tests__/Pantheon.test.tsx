import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'

import { Pantheon } from '../Pantheon'
import type { OrgSummary } from '@/lib/types'

// ---- fixtures ----------------------------------------------------------------

function makeOrg(overrides: Partial<OrgSummary> & Pick<OrgSummary, 'id' | 'name' | 'status'>): OrgSummary {
  return {
    purpose: 'テスト組織の目的',
    target_repo_path: null,
    health_score: 70,
    autonomy_score: 60,
    improvement_velocity: 1,
    total_agents: 2,
    pending_proposals: 0,
    last_active: '2026-06-16T00:00:00Z',
    is_system: false,
    icon_data: null,
    ...overrides,
  }
}

// A: active, no pending, not system
const orgA = makeOrg({ id: 'org-a', name: 'Org Alpha', status: 'active', pending_proposals: 0, is_system: false })
// B: paused, has pending proposals, not system
const orgB = makeOrg({ id: 'org-b', name: 'Org Beta', status: 'paused', pending_proposals: 3, is_system: false })
// C: archived, no pending, is_system
const orgC = makeOrg({ id: 'org-c', name: 'Org Gamma', status: 'archived', pending_proposals: 0, is_system: true })

const allOrgs: OrgSummary[] = [orgA, orgB, orgC]

// ---- helpers -----------------------------------------------------------------

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/organizations')) {
      return { ok: true, json: async () => allOrgs }
    }
    return { ok: true, json: async () => [] }
  }) as unknown as typeof fetch
})

// ---- tests -------------------------------------------------------------------

describe('Pantheon organisation catalog filter regression', () => {
  it('all フィルタ（既定）: A / B / C 全組織名が表示される', async () => {
    render(<Pantheon />)

    await waitFor(() => {
      expect(screen.getByText('Org Alpha')).toBeInTheDocument()
    })
    expect(screen.getByText('Org Beta')).toBeInTheDocument()
    expect(screen.getByText('Org Gamma')).toBeInTheDocument()
  })

  it('live フィルタ: active な A と pending>0 な B が表示、archived+pending=0 の C は非表示', async () => {
    render(<Pantheon />)

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Org Alpha')).toBeInTheDocument()
    })

    // Click "live" filter button
    fireEvent.click(screen.getByRole('button', { name: 'live' }))

    // A (active) → visible
    expect(screen.getByText('Org Alpha')).toBeInTheDocument()
    // B (paused but pending_proposals=3) → visible
    expect(screen.getByText('Org Beta')).toBeInTheDocument()
    // C (archived, pending=0, is_system) → hidden
    expect(screen.queryByText('Org Gamma')).not.toBeInTheDocument()
  })

  it('system フィルタ: is_system な C だけ表示、A / B は非表示', async () => {
    render(<Pantheon />)

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Org Alpha')).toBeInTheDocument()
    })

    // Click "system" filter button
    fireEvent.click(screen.getByRole('button', { name: 'system' }))

    // C (is_system=true) → visible
    expect(screen.getByText('Org Gamma')).toBeInTheDocument()
    // A and B → hidden
    expect(screen.queryByText('Org Alpha')).not.toBeInTheDocument()
    expect(screen.queryByText('Org Beta')).not.toBeInTheDocument()
  })
})

describe('Pantheon metric meters surfacing', () => {
  // 各プレートの lede は「健全度・自律度・改善速度」を約束する。
  // improvement_velocity はバックエンドが返す（0〜100 にクランプ済み）が、
  // 以前は描画されていなかった回帰を防ぐ。
  const soloOrg = makeOrg({
    id: 'org-solo',
    name: 'Org Solo',
    status: 'active',
    health_score: 70,
    autonomy_score: 60,
    improvement_velocity: 42,
  })

  beforeEach(() => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/organizations')) {
        return { ok: true, json: async () => [soloOrg] }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch
  })

  it('OrgPlate は健全度・自律度・改善速度の3メーターを描画し、改善速度に improvement_velocity を束ねる', async () => {
    render(<Pantheon />)

    await waitFor(() => {
      expect(screen.getByText('Org Solo')).toBeInTheDocument()
    })

    // 3 つのメーター（progressbar）が揃う
    expect(screen.getByRole('progressbar', { name: '健全度' })).toHaveAttribute('aria-valuenow', '70')
    expect(screen.getByRole('progressbar', { name: '自律度' })).toHaveAttribute('aria-valuenow', '60')

    // 改善速度メーターが存在し、improvement_velocity の値を反映する（本修正の主眼）
    const velocityMeter = screen.getByRole('progressbar', { name: '改善速度' })
    expect(velocityMeter).toHaveAttribute('aria-valuenow', '42')
  })
})
