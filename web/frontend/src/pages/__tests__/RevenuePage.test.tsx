import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { RevenuePage } from '../RevenuePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

type Metrics = {
  orgs: {
    org_name: string
    reach: number
    revenue: number
    posts: number
    reach_but_no_revenue: boolean
  }[]
  total_revenue: number
  total_reach: number
}
type Report = { by_month: Record<string, number>; total_revenue: number }
type Intel = {
  trend: 'growing' | 'flat' | 'declining' | 'insufficient'
  latest_change_pct: number | null
  forecast_next: number
}

const metrics: Metrics = {
  orgs: [
    { org_name: 'Note Sales', reach: 5000, revenue: 0, posts: 3, reach_but_no_revenue: true },
    { org_name: 'Affiliate Revenue', reach: 2000, revenue: 12000, posts: 5, reach_but_no_revenue: false },
  ],
  total_revenue: 12000,
  total_reach: 7000,
}

const report: Report = {
  by_month: { '2026-05': 1500, '2026-06': 2000 },
  total_revenue: 3500,
}

const intel: Intel = { trend: 'growing', latest_change_pct: 33.3, forecast_next: 2666 }
const portfolio = {
  proposals: [
    { kind: 'portfolio_allocation', title: '[HQ提案] Note Sales を monetize', reason: '収益化が必要', priority: 2 },
  ],
}

const emptyMetrics: Metrics = { orgs: [], total_revenue: 0, total_reach: 0 }
const emptyReport: Report = { by_month: {}, total_revenue: 0 }
const insufficientIntel: Intel = { trend: 'insufficient', latest_change_pct: null, forecast_next: 0 }

/** mockApi をパス別に応答させる（load は revenue / report / intelligence / hq portfolio を並列取得）。 */
function wireApi(opts?: { metrics?: Metrics; report?: Report; intel?: Intel }) {
  const m = opts?.metrics ?? metrics
  const r = opts?.report ?? report
  const ai = opts?.intel ?? intel
  mockApi.mockImplementation((_method: string, path: string) => {
    if (path === '/api/metrics/revenue') return Promise.resolve(m)
    if (path === '/api/metrics/revenue/report') return Promise.resolve(r)
    if (path === '/api/metrics/revenue/intelligence') return Promise.resolve(ai)
    if (path === '/api/hq/portfolio') return Promise.resolve(portfolio)
    if (path === '/api/hq/portfolio/scan') return Promise.resolve({ proposals: 2 })
    if (path === '/api/outcomes') return Promise.resolve({ ok: true, event: {} })
    return Promise.resolve({})
  })
}

it('累計収益とリーチのカードを表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  expect(await screen.findByText('¥12,000')).toBeInTheDocument()
  expect(screen.getByText('7,000')).toBeInTheDocument()
})

it('「リーチ有・収益0」の組織をアラート表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  expect(await screen.findByText('リーチはあるが収益0の組織（収益化の余地）')).toBeInTheDocument()
  expect(screen.getAllByText('Note Sales').length).toBeGreaterThan(0)
})

it('成果データが無いとき空状態を表示する', async () => {
  wireApi({ metrics: emptyMetrics, report: emptyReport, intel: insufficientIntel })
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('成果データがありません')).toBeInTheDocument()
})

it('収益トレンド（成長・前月比・翌月予測）を表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('収益トレンド（全組織）')).toBeInTheDocument()
  expect(screen.getByText('成長')).toBeInTheDocument()
  expect(screen.getByText('+33.3%')).toBeInTheDocument()
})

it('ポートフォリオ提案（HQ）を表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('ポートフォリオ提案（HQ）')).toBeInTheDocument()
  expect(screen.getByText('[HQ提案] Note Sales を monetize')).toBeInTheDocument()
})

it('自律経営プラン: 目標額を入れてプランを起票する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  await screen.findByText('自律経営プラン（月収益目標）')
  fireEvent.change(screen.getByPlaceholderText('月次目標額（円）'), { target: { value: '100000' } })
  fireEvent.click(screen.getByRole('button', { name: 'プランを起票' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/hq/portfolio/scan', { target: 100000 })
  )
})

it('月次収益レポートを表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('月次収益レポート（全組織）')).toBeInTheDocument()
  expect(screen.getByText('2026-05')).toBeInTheDocument()
  expect(screen.getByText('¥2,000')).toBeInTheDocument()
})

it('手動入力フォームから POST /api/outcomes を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  await screen.findByText('収益・成果を手動で記録')

  fireEvent.change(screen.getByPlaceholderText('組織名'), { target: { value: 'Note Sales' } })
  fireEvent.change(screen.getByPlaceholderText('0'), { target: { value: '7000' } })
  fireEvent.click(screen.getByRole('button', { name: '記録' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/outcomes', {
      org_name: 'Note Sales',
      metric: 'revenue',
      value: 7000,
      note: '',
    })
  )
})
