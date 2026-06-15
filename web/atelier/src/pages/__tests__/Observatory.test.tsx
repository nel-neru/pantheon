import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { Observatory } from '../Observatory'
import type { DaemonsPayload, OrchestraData, OrgSummary, UsageSummary } from '@/lib/types'

// ---- fixtures ----------------------------------------------------------------

const orchestra: OrchestraData = {
  // pending_handoffs=4 (not 3): with pending_proposals=2 this makes pendingReview=6 — a value
  // that does NOT collide with any other rendered figure (agents=5, orgs=1, sessions=2), so the
  // assertion genuinely pins the sum. (agents=5 would have masked a pendingReview=5 collision.)
  counts: { sessions: 1, active_sessions: 2, agents: 5, handoffs: 1, pending_handoffs: 4 },
  sessions: [],
  handoffs: [],
}

const orgList: OrgSummary[] = [
  {
    id: 'org-1',
    name: 'Alpha Org',
    purpose: 'テスト組織',
    target_repo_path: null,
    status: 'active',
    health_score: 80,
    autonomy_score: 70,
    improvement_velocity: 1,
    total_agents: 3,
    pending_proposals: 2,
    last_active: '2026-06-16T00:00:00Z',
    is_system: false,
    icon_data: null,
  },
]

const usageOk: UsageSummary = {
  usage: {
    session_5h: {
      window_hours: 5,
      calls: 10,
      input_tokens: 5000,
      output_tokens: 3000,
      cache_read_tokens: 0,
      total_tokens: 8000,
      total_cost_usd: 0.5,
      measured_calls: 10,
      estimated_calls: 0,
    },
  },
  governor: { enabled: true, level: 'ok', window_hours: 5, window_tokens: 100000, soft_limit_tokens: 80000, hard_limit_tokens: 95000 },
  // rate_limited omitted intentionally — leave undefined so daemons.rate_limited can be the
  // source of truth without being short-circuited by a false value on usage.
}

const daemonsOk: DaemonsPayload = {
  daemons: [
    { name: 'improvement', running: true, stale: false, enabled: true },
    { name: 'content', running: false },
    { name: 'trend', running: true, stale: true },
  ],
  rate_limited: false,
}

// ---- helpers -----------------------------------------------------------------

function renderObservatory() {
  return render(
    <MemoryRouter>
      <Observatory />
    </MemoryRouter>,
  )
}

function mockFetch({
  usagePayload = usageOk as UsageSummary | null,
  daemonsPayload = daemonsOk,
  usageOkFlag = true,
}: {
  usagePayload?: UsageSummary | null
  daemonsPayload?: DaemonsPayload
  usageOkFlag?: boolean
} = {}) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/dashboard/orchestra')) {
      return { ok: true, json: async () => orchestra }
    }
    if (url.includes('/api/organizations')) {
      return { ok: true, json: async () => orgList }
    }
    if (url.includes('/api/usage/summary')) {
      if (!usageOkFlag) {
        return { ok: false, status: 503, json: async () => ({ detail: 'down' }) }
      }
      return { ok: true, json: async () => usagePayload }
    }
    if (url.includes('/api/daemons/status')) {
      return { ok: true, json: async () => daemonsPayload }
    }
    return { ok: true, json: async () => [] }
  }) as unknown as typeof fetch
}

// ---- tests -------------------------------------------------------------------

describe('Observatory regression tests', () => {
  beforeEach(() => {
    mockFetch()
  })

  it('pendingReview: pending_proposals 合計(2) + pending_handoffs(4) = 6 が "Pending Review" に表示される', async () => {
    // orgList has pending_proposals=2; orchestra has pending_handoffs=4 → total=6
    renderObservatory()
    await waitFor(() => {
      expect(screen.getByText('Pending Review')).toBeInTheDocument()
    })
    // 6 is unique among all rendered figures (agents=5, orgs=1, sessions=2), so this
    // unambiguously pins the pendingReview sum — a broken sum would not produce 6.
    expect(screen.getByText('6')).toBeInTheDocument()
  })

  it('usageDown graceful degradation: /api/usage/summary が 503 のとき "—" が表示され、他カードは正常', async () => {
    mockFetch({ usageOkFlag: false })
    renderObservatory()

    // Tokens · 5h stat should show "—" as its value
    await waitFor(() => {
      // The label
      expect(screen.getByText('Tokens · 5h')).toBeInTheDocument()
    })

    // The value "—" appears (could be multiple places but at least one)
    await waitFor(() => {
      expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    })

    // The sub "governor: —" should appear
    await waitFor(() => {
      expect(screen.getByText('governor: —')).toBeInTheDocument()
    })

    // Other stat: "Organizations" label and its value (1 org) still visible
    expect(screen.getByText('Organizations')).toBeInTheDocument()

    // Page hasn't crashed — header still present
    expect(screen.getByText('The Observatory')).toBeInTheDocument()
  })

  it('rate-limited 表示: daemons.rate_limited=true のとき Systems ヘッダに "rate-limited" タグが出る', async () => {
    mockFetch({ daemonsPayload: { ...daemonsOk, rate_limited: true } })
    renderObservatory()

    await waitFor(() => {
      expect(screen.getByText('rate-limited')).toBeInTheDocument()
    })

    // Systems heading still visible
    expect(screen.getByText('Systems')).toBeInTheDocument()
  })

  it('デーモン状態ラベル: 稼働 / 停止 / stale / paused の4分岐が正しく出る', async () => {
    mockFetch({
      daemonsPayload: {
        daemons: [
          { name: 'improvement', running: true, stale: false, enabled: true },
          { name: 'content', running: false },
          { name: 'trend', running: true, stale: true },
          // running かつ not-stale だが enabled===false → "paused"（Observatory.tsx:201 の第3分岐）
          { name: 'revenue', running: true, stale: false, enabled: false },
        ],
        rate_limited: false,
      },
    })
    renderObservatory()

    // Wait until daemon list renders (Systems section loads)
    await waitFor(() => {
      expect(screen.getByText('稼働')).toBeInTheDocument()
    })

    expect(screen.getByText('停止')).toBeInTheDocument()
    expect(screen.getByText('stale')).toBeInTheDocument()
    expect(screen.getByText('paused')).toBeInTheDocument()

    // Daemon names are in the DOM as-is (CSS text-transform uppercase is not applied by jsdom).
    // The label strings match the original name values from the API payload.
    expect(screen.getByText('improvement')).toBeInTheDocument()
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.getByText('trend')).toBeInTheDocument()
  })
})
