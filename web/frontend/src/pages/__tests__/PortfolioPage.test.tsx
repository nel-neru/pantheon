import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { PortfolioPage } from '../PortfolioPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

// ─── Fixture factories ────────────────────────────────────────────────────────

/** 最小の overview レスポンス（空状態）。 */
const emptyOverview = {
  orgs: [],
  org_count: 0,
  total_revenue: 0,
  total_reach: 0,
  pending_handoffs: 0,
  new_business_candidates: 0,
}

/** 複数 org の overview（ROI 降順テスト用）。 */
const overviewWithOrgs = {
  orgs: [
    {
      org_name: 'High ROI Org',
      revenue: 120000,
      reach: 1000,
      roi: 120,
      action: 'invest',
      revenue_percentile: 90,
      roi_percentile: 95,
      flag: 'top_performer',
    },
    {
      org_name: 'Low ROI Org',
      revenue: 5000,
      reach: 8000,
      roi: 0.625,
      action: 'grow_audience',
      revenue_percentile: 20,
      roi_percentile: 10,
      flag: 'underperformer',
    },
    {
      org_name: 'Mid ROI Org',
      revenue: 30000,
      reach: 3000,
      roi: 10,
      action: 'optimize',
      revenue_percentile: 55,
      roi_percentile: 50,
      flag: '',
    },
  ],
  org_count: 3,
  total_revenue: 155000,
  total_reach: 12000,
  pending_handoffs: 2,
  new_business_candidates: 1,
}

/** API をパス別に応答させるヘルパー。 */
function wireApi(overview: unknown = emptyOverview) {
  mockApi.mockImplementation((_method: string, path: string) => {
    if (path === '/api/portfolio/overview') return Promise.resolve(overview)
    return Promise.resolve({})
  })
}

// ─── 空状態 ───────────────────────────────────────────────────────────────────

it('空状態: KPI 行を表示する（0 値で描画）', async () => {
  wireApi(emptyOverview)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('kpi-row')
  expect(screen.getByText('組織数')).toBeInTheDocument()
  expect(screen.getByText('累計収益')).toBeInTheDocument()
  expect(screen.getByText('累計リーチ')).toBeInTheDocument()
  expect(screen.getByText('引き渡し待ち')).toBeInTheDocument()
  expect(screen.getByText('新規事業候補')).toBeInTheDocument()
})

it('空状態: 組織テーブルの代わりに空メッセージを表示する', async () => {
  wireApi(emptyOverview)
  renderWithRouter(<PortfolioPage />)

  expect(await screen.findByTestId('orgs-empty')).toBeInTheDocument()
  expect(screen.queryByTestId('org-table')).not.toBeInTheDocument()
})

it('空状態: 機会コールアウトを表示しない（pending_handoffs=0, new_business_candidates=0）', async () => {
  wireApi(emptyOverview)
  renderWithRouter(<PortfolioPage />)

  // orgs-empty が描画される（ロード完了の確認）
  await screen.findByTestId('orgs-empty')
  expect(screen.queryByTestId('opportunity-callout')).not.toBeInTheDocument()
})

// ─── KPI 表示 ────────────────────────────────────────────────────────────────

it('KPI: org_count / total_revenue / total_reach / pending_handoffs / new_business_candidates を表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('kpi-row')

  // org_count=3
  expect(screen.getByText('3')).toBeInTheDocument()
  // total_revenue=155000 → ¥155,000
  expect(screen.getByText('¥155,000')).toBeInTheDocument()
  // total_reach=12000 → 12,000
  expect(screen.getByText('12,000')).toBeInTheDocument()
  // pending_handoffs=2 と new_business_candidates=1 が数値として表示される
  expect(screen.getByText('2')).toBeInTheDocument()
  expect(screen.getByText('1')).toBeInTheDocument()
})

// ─── 機会コールアウト ─────────────────────────────────────────────────────────

it('機会コールアウト: pending_handoffs > 0 のとき表示する', async () => {
  wireApi(overviewWithOrgs) // pending_handoffs=2
  renderWithRouter(<PortfolioPage />)

  expect(await screen.findByTestId('opportunity-callout')).toBeInTheDocument()
  expect(screen.getByText('承認待ちの機会があります')).toBeInTheDocument()
})

it('機会コールアウト: 承認インボックスとマーケットプレイスへのリンクを表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('opportunity-callout')
  expect(screen.getByRole('button', { name: /承認インボックスを開く/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /マーケットプレイス/ })).toBeInTheDocument()
})

it('機会コールアウト: 件数の内訳を表示する', async () => {
  wireApi(overviewWithOrgs) // pending_handoffs=2, new_business_candidates=1
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('opportunity-callout')
  expect(screen.getByText(/引き渡し待ち 2 件/)).toBeInTheDocument()
  expect(screen.getByText(/新規事業候補 1 件/)).toBeInTheDocument()
})

// ─── ROI 降順ソート ───────────────────────────────────────────────────────────

it('ROI 降順: テーブルの行順が ROI 降順になっている（High → Mid → Low）', async () => {
  wireApi(overviewWithOrgs) // orgs は ROI=120, 0.625, 10 の順（バックエンドが既にソート済み想定外でもテスト）
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')

  const rows = screen.getAllByRole('row')
  // rows[0] = thead tr, rows[1..] = tbody tr
  const bodyRows = rows.slice(1)
  const firstCell = bodyRows[0].querySelector('td')?.textContent ?? ''
  const secondCell = bodyRows[1].querySelector('td')?.textContent ?? ''
  const thirdCell = bodyRows[2].querySelector('td')?.textContent ?? ''

  expect(firstCell).toContain('High ROI Org')
  expect(secondCell).toContain('Mid ROI Org')
  expect(thirdCell).toContain('Low ROI Org')
})

// ─── フラグバッジ ─────────────────────────────────────────────────────────────

it('flag=top_performer の組織に ★ バッジを表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  // aria-label でアクセスする
  expect(screen.getByLabelText('トップパフォーマー')).toBeInTheDocument()
})

it('flag=underperformer の組織に ⚠ バッジを表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  expect(screen.getByLabelText('改善が必要')).toBeInTheDocument()
})

it('flag が空の組織にはフラグバッジを表示しない', async () => {
  wireApi(overviewWithOrgs) // Mid ROI Org の flag = ''
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  // Mid ROI Org の行にはフラグなし（★ は 1 つだけ）
  expect(screen.getAllByLabelText('トップパフォーマー')).toHaveLength(1)
})

// ─── 推奨アクションの日本語ラベル ────────────────────────────────────────────

it('action=invest を「強化投資」として表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  expect(screen.getByText('強化投資')).toBeInTheDocument()
})

it('action=grow_audience を「リーチ拡大」として表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  expect(screen.getByText('リーチ拡大')).toBeInTheDocument()
})

it('action=optimize を「効率改善」として表示する', async () => {
  wireApi(overviewWithOrgs)
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  expect(screen.getByText('効率改善')).toBeInTheDocument()
})

it('revenue_percentile を「xx%」形式で表示する', async () => {
  wireApi(overviewWithOrgs) // High ROI Org: revenue_percentile=90
  renderWithRouter(<PortfolioPage />)

  await screen.findByTestId('org-table')
  expect(screen.getByText('90%')).toBeInTheDocument()
})

// ─── NaN / missing フィールドの coerce ───────────────────────────────────────

it('数値フィールドが null/undefined/string でもクラッシュしない', async () => {
  const badOverview = {
    orgs: [
      {
        org_name: 'Broken Org',
        revenue: null,
        reach: undefined,
        roi: 'bad',
        action: '',
        revenue_percentile: NaN,
        roi_percentile: null,
        flag: '',
      },
    ],
    org_count: null,
    total_revenue: undefined,
    total_reach: 'invalid',
    pending_handoffs: null,
    new_business_candidates: undefined,
  }
  wireApi(badOverview)
  renderWithRouter(<PortfolioPage />)

  // クラッシュしないことと、組織名が表示されること
  expect(await screen.findByText('Broken Org')).toBeInTheDocument()
})

it('API が null を返してもクラッシュしない', async () => {
  mockApi.mockImplementation((_method: string, path: string) => {
    if (path === '/api/portfolio/overview') return Promise.resolve(null)
    return Promise.resolve({})
  })
  renderWithRouter(<PortfolioPage />)

  // null レスポンスでも空状態を描画してクラッシュしないこと
  await waitFor(() => {
    // loading が終わると空テーブルメッセージまたは KPI が表示される
    expect(screen.queryByText('ポートフォリオデータを読み込み中…')).not.toBeInTheDocument()
  })
})

it('api が配列でない orgs を返しても空テーブルにフォールバックする', async () => {
  wireApi({ orgs: null, org_count: 0, total_revenue: 0, total_reach: 0, pending_handoffs: 0, new_business_candidates: 0 })
  renderWithRouter(<PortfolioPage />)

  expect(await screen.findByTestId('orgs-empty')).toBeInTheDocument()
})

// ─── エラー状態 ───────────────────────────────────────────────────────────────

it('API エラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<PortfolioPage />)

  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})
