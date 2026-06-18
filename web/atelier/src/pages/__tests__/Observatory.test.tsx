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
  orchestraOkFlag = true,
}: {
  usagePayload?: UsageSummary | null
  daemonsPayload?: DaemonsPayload
  usageOkFlag?: boolean
  orchestraOkFlag?: boolean
} = {}) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/dashboard/orchestra')) {
      if (!orchestraOkFlag) {
        return { ok: false, status: 503, json: async () => ({ detail: 'down' }) }
      }
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

  it('orchestraDown パリティ: /api/dashboard/orchestra が 503 でも orgs が健全なら、live 系を 0 と偽装せず "フィード未取得" を開示する', async () => {
    // orchestra フィードだけダウン（orgs/usage/daemons は健全）。これは「両方エラー」ガードを
    // 通過してページが描画される partial-degradation。counts が undefined で sessions/agents/
    // handoffs は 0 に潰れるが、それを「真の 0（= idle）」として見せてはいけない。
    mockFetch({ orchestraOkFlag: false })
    renderObservatory()

    // Live Agents の sub が "フィード未取得" になり、down を開示している
    await waitFor(() => {
      expect(screen.getByText('フィード未取得')).toBeInTheDocument()
    })

    // Firmament のタグが偽りの "Live" ではなく "feed down" を表示する
    expect(screen.getByText('Firmament · feed down')).toBeInTheDocument()
    expect(screen.queryByText('Firmament · Live')).not.toBeInTheDocument()

    // orchestra 由来の数値（Live Agents 値・稼働セッション/エージェント/引き渡しの caption）が
    // 0 ではなく "—"。usage は健全なので "—" は orchestra 由来のみ＝4 箇所以上。
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)

    // Pending Review の sub は handoffs 項が落ちたことを開示する＝"提案 + 引き渡し" と
    // 過大主張しない（値自体は提案数の実データなので残る）。
    expect(screen.getByText('提案のみ（引き渡しはフィード未取得）')).toBeInTheDocument()
    expect(screen.queryByText('提案 + 引き渡し')).not.toBeInTheDocument()

    // 全ページ ErrorNote（"接続エラー"）には落ちていない＝partial 経路で描画されている
    expect(screen.queryByText('接続エラー')).not.toBeInTheDocument()

    // orgs は健全なので Observatory ヘッダと Organizations カードは生きている
    expect(screen.getByText('The Observatory')).toBeInTheDocument()
    expect(screen.getByText('Organizations')).toBeInTheDocument()
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

  // ---- GovernorBudget tests ---------------------------------------------------

  it('governor soft_limit: キャプション・バー fill・ソフトマーカーが描画される', async () => {
    const usageSoftLimit: UsageSummary = {
      ...usageOk,
      governor: {
        enabled: true,
        level: 'soft_limit',
        window_hours: 5,
        window_tokens: 35000,
        soft_limit_tokens: 30000,
        hard_limit_tokens: 50000,
      },
    }
    mockFetch({ usagePayload: usageSoftLimit })
    renderObservatory()

    // caption: compactNumber(35000)='35.0k', compactNumber(50000)='50.0k', compactNumber(30000)='30.0k'
    await waitFor(() => {
      expect(screen.getByText(/35\.0k/)).toBeInTheDocument()
    })
    expect(screen.getByText(/50\.0k.*トークン/)).toBeInTheDocument()
    expect(screen.getByText(/ソフト.*30\.0k/)).toBeInTheDocument()
    expect(screen.getByText(/5h窓/)).toBeInTheDocument()

    // bar fill element exists
    expect(screen.getByTestId('gov-budget-fill')).toBeInTheDocument()
    // soft marker exists (soft_limit_tokens=30000 < hard=50000)
    expect(screen.getByTestId('gov-soft-marker')).toBeInTheDocument()
  })

  it('governor disabled: "ガバナー無効" テキストが出て、バー fill は存在しない', async () => {
    const usageDisabled: UsageSummary = {
      ...usageOk,
      governor: {
        enabled: false,
        level: 'ok',
        window_hours: 5,
        window_tokens: 0,
        soft_limit_tokens: 0,
        hard_limit_tokens: 0,
      },
    }
    mockFetch({ usagePayload: usageDisabled })
    renderObservatory()

    await waitFor(() => {
      expect(screen.getByText('ガバナー無効（上限なし）')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('gov-budget-fill')).not.toBeInTheDocument()
  })

  it('usageDown: 予算 readout が描画されない（caption も "ガバナー無効" もなし）', async () => {
    mockFetch({ usageOkFlag: false })
    renderObservatory()

    await waitFor(() => {
      // The page still renders (header visible)
      expect(screen.getByText('The Observatory')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('gov-budget-fill')).not.toBeInTheDocument()
    expect(screen.queryByText(/ガバナー無効/)).not.toBeInTheDocument()
    // no budget caption rendered (no "トークン" text in budget area)
    expect(screen.queryByText(/トークン.*窓/)).not.toBeInTheDocument()
  })

  it('over-limit: window_tokens > hard_limit_tokens のとき fill width が 100%、caption は実数値', async () => {
    const usageOverLimit: UsageSummary = {
      ...usageOk,
      governor: {
        enabled: true,
        level: 'hard_limit',
        window_hours: 5,
        window_tokens: 60000,
        soft_limit_tokens: 30000,
        hard_limit_tokens: 50000,
      },
    }
    mockFetch({ usagePayload: usageOverLimit })
    renderObservatory()

    // caption shows real window_tokens (60.0k) not clamped
    await waitFor(() => {
      expect(screen.getByText(/60\.0k/)).toBeInTheDocument()
    })
    // hard_limit also in caption
    expect(screen.getByText(/50\.0k.*トークン/)).toBeInTheDocument()

    // bar fill is clamped to 100%
    const fill = screen.getByTestId('gov-budget-fill')
    expect(fill).toBeInTheDocument()
    expect((fill as HTMLElement).style.width).toBe('100%')
  })

  it('部分 governor ペイロード: window_tokens 欠落でも fill width が NaN% にならず 0% へ寄る', async () => {
    // governor は free-form JSON 由来でフィールド欠落がありうる（型は非 optional だが実体は別）。
    // 欠落フィールドが算術に乗ると width:'NaN%' でバーが壊れるため、finite coercion を検証する。
    const usagePartial = {
      ...usageOk,
      governor: {
        enabled: true,
        level: 'ok',
        window_hours: 5,
        // window_tokens を意図的に欠落させる
        soft_limit_tokens: 30000,
        hard_limit_tokens: 50000,
      },
    } as unknown as UsageSummary
    mockFetch({ usagePayload: usagePartial })
    renderObservatory()

    const fill = await screen.findByTestId('gov-budget-fill')
    expect((fill as HTMLElement).style.width).toBe('0%')
    expect((fill as HTMLElement).style.width).not.toContain('NaN')
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
