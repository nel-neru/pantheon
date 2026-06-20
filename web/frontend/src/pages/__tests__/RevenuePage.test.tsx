import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
    { kind: 'monetization', title: '[HQ提案] Note Sales を monetize', reason: '収益化が必要', priority: 2 },
    { kind: 'traffic', title: '[HQ提案] Affiliate へ送客', reason: 'リーチ余剰', priority: 1 },
  ],
}

const emptyMetrics: Metrics = { orgs: [], total_revenue: 0, total_reach: 0 }
const emptyReport: Report = { by_month: {}, total_revenue: 0 }
const insufficientIntel: Intel = { trend: 'insufficient', latest_change_pct: null, forecast_next: 0 }

const daemonsStatus = {
  daemons: {
    revenue: { name: 'revenue', running: false, pid: null, last_heartbeat: null },
  },
}

const daemonsStatusRunning = {
  daemons: {
    revenue: { name: 'revenue', running: true, pid: 1234, last_heartbeat: '2026-06-20T10:00:00Z' },
  },
}

/** mockApi をパス別に応答させる（load は revenue / report / intelligence / hq portfolio / daemons を並列取得）。 */
function wireApi(opts?: { metrics?: Metrics; report?: Report; intel?: Intel; daemonRunning?: boolean }) {
  const m = opts?.metrics ?? metrics
  const r = opts?.report ?? report
  const ai = opts?.intel ?? intel
  const ds = opts?.daemonRunning ? daemonsStatusRunning : daemonsStatus
  mockApi.mockImplementation((_method: string, path: string, body?: unknown) => {
    if (path === '/api/metrics/revenue') return Promise.resolve(m)
    if (path === '/api/metrics/revenue/report') return Promise.resolve(r)
    if (path === '/api/metrics/revenue/intelligence') return Promise.resolve(ai)
    if (path === '/api/hq/portfolio') return Promise.resolve(portfolio)
    if (path === '/api/daemons/status') return Promise.resolve(ds)
    if (path === '/api/hq/portfolio/scan') return Promise.resolve({ proposals: 2 })
    if (path.startsWith('/api/hq/portfolio/plan')) {
      return Promise.resolve({
        gap: {
          target: 100000,
          current: 2000,
          forecast: 2666,
          present_gap: 98000,
          forecast_gap: 97334,
          under_target: true,
        },
        plan: [
          { kind: 'monetization', title: '[プラン] 収益化を強化する打ち手', reason: 'プレビュー専用の理由', priority: 2 },
        ],
      })
    }
    if (path === '/api/outcomes') return Promise.resolve({ ok: true, event: {} })
    if (path === '/api/daemons/revenue/start') return Promise.resolve({ name: 'revenue', status: 'started' })
    if (path === '/api/daemons/revenue/stop') return Promise.resolve({ name: 'revenue', status: 'stopped' })
    if (path === '/api/outcomes/import') {
      const b = body as { rows?: unknown[] } | undefined
      return Promise.resolve({ imported: b?.rows?.length ?? 0, skipped: 0, orgs: ['My Co'] })
    }
    return Promise.resolve({})
  })
}


// ── 基本表示 ──────────────────────────────────────────────────────────────────

it('累計収益とリーチのカードを表示する（formatYen/formatNumber 経由）', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  // ¥12,000 は KPI カードと組織テーブル両方に出るので getAllByText で複数可とする
  const revenueEls = await screen.findAllByText('¥12,000')
  expect(revenueEls.length).toBeGreaterThan(0)
  // 7,000 は累計リーチカードに表示される
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

// ── 空状態から手動フォームへの導線 ──────────────────────────────────────────

it('空状態に「手動記録フォームへ」ボタンを表示する', async () => {
  wireApi({ metrics: emptyMetrics, report: emptyReport, intel: insufficientIntel })
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByRole('button', { name: /手動記録フォームへ/ })).toBeInTheDocument()
})

// ── 収益トレンド ──────────────────────────────────────────────────────────────

it('収益トレンド（成長・前月比・翌月予測）を表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('収益トレンド（全組織）')).toBeInTheDocument()
  expect(screen.getByText('成長')).toBeInTheDocument()
  // +33.3% は trend card と monthly report 両方に出る可能性がある
  expect(screen.getAllByText('+33.3%').length).toBeGreaterThan(0)
})

it('トレンドが insufficient でも trend-card を（データ蓄積中として）表示する', async () => {
  wireApi({ intel: insufficientIntel })
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('収益トレンド（全組織）')).toBeInTheDocument()
  expect(screen.getByText(/データ蓄積中/)).toBeInTheDocument()
})

// ── ポートフォリオ提案 ────────────────────────────────────────────────────────

it('ポートフォリオ提案（HQ）を priority 降順で表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('ポートフォリオ提案（HQ）')).toBeInTheDocument()
  expect(screen.getByText('[HQ提案] Note Sales を monetize')).toBeInTheDocument()

  // priority:2 の提案が priority:1 より先に来ること
  const rows = screen.getAllByText(/HQ提案/)
  expect(rows[0].textContent).toContain('Note Sales')
})

it('ポートフォリオ提案行に kind の和訳バッジを表示する（英語ラベル露出なし）', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('ポートフォリオ提案（HQ）')
  // 'monetization' ではなく '収益化' が表示される
  expect(screen.getByText('収益化')).toBeInTheDocument()
  // 'traffic' ではなく '送客' が表示される
  expect(screen.getByText('送客')).toBeInTheDocument()
})

it('ポートフォリオ提案行に「承認インボックスで開く」ボタンがある', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('ポートフォリオ提案（HQ）')
  // 複数行あるので getAllByRole
  const buttons = screen.getAllByRole('button', { name: /承認インボックスで開く/ })
  expect(buttons.length).toBeGreaterThan(0)
})

// ── 自律経営プラン ────────────────────────────────────────────────────────────

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

it('自律経営プラン: 「プランをプレビュー」は起票せず GET プレビューを呼び、ギャップと打ち手を表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  await screen.findByText('自律経営プラン（月収益目標）')
  fireEvent.change(screen.getByPlaceholderText('月次目標額（円）'), { target: { value: '100000' } })
  fireEvent.click(screen.getByRole('button', { name: 'プランをプレビュー' }))

  // 非破壊の GET を呼ぶ（起票の scan POST は呼ばない）
  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/hq/portfolio/plan?target=100000')
  )
  expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/hq/portfolio/scan', expect.anything())

  // ギャップ（目標¥100,000・ギャップ¥98,000）と打ち手をプレビュー表示
  expect(await screen.findByText('プランプレビュー（未起票）')).toBeInTheDocument()
  expect(screen.getByText('¥98,000')).toBeInTheDocument()
  expect(screen.getByText('[プラン] 収益化を強化する打ち手')).toBeInTheDocument()
})

it('自律経営プラン: プレビュー前は plan-preview を描画しない', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  await screen.findByText('自律経営プラン（月収益目標）')
  expect(screen.queryByText('プランプレビュー（未起票）')).not.toBeInTheDocument()
})

it('自律経営プラン: Enter キーでも起票できる', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)

  await screen.findByText('自律経営プラン（月収益目標）')
  const input = screen.getByPlaceholderText('月次目標額（円）')
  fireEvent.change(input, { target: { value: '50000' } })
  fireEvent.keyDown(input, { key: 'Enter' })

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/hq/portfolio/scan', { target: 50000 })
  )
})

// ── 月次収益レポート ──────────────────────────────────────────────────────────

it('月次収益レポートを表示する（month キーソート順）', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('月次収益レポート（全組織）')).toBeInTheDocument()
  expect(screen.getByText('2026-05')).toBeInTheDocument()
  expect(screen.getByText('¥2,000')).toBeInTheDocument()
})

it('月次データが空のとき「月次データが蓄積されると表示されます」を出す', async () => {
  wireApi({ report: emptyReport })
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('月次収益レポート（全組織）')).toBeInTheDocument()
  expect(screen.getByText(/月次データが蓄積/)).toBeInTheDocument()
})

it('月次収益レポートに前月比列を表示する', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  // '前月比' はトレンドカードのスパンとテーブルヘッダ両方に出るので getAllByText で複数可とする
  const headerEls = await screen.findAllByText('前月比')
  expect(headerEls.length).toBeGreaterThan(0)
  // 2026-06 の前月比 = (2000-1500)/1500 ≈ +33.3%。
  // trend card にも同値が出る可能性があるので getAllByText で複数可とする。
  const pcts = screen.getAllByText('+33.3%')
  expect(pcts.length).toBeGreaterThan(0)
})

// ── 収益化余地アラート ────────────────────────────────────────────────────────

it('収益化余地アラートのボタンが組織名を URL クエリに含む', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('リーチはあるが収益0の組織（収益化の余地）')
  const btn = screen.getByRole('button', { name: /Note Sales の引き渡しを確認/ })
  expect(btn).toBeInTheDocument()
})

// ── 手動入力フォーム ──────────────────────────────────────────────────────────

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

it('メトリクス選択の option に日本語ラベルが表示される', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('収益・成果を手動で記録')
  // select の option テキストは screen.getByRole('option', ...) でアクセスできる
  expect(screen.getByRole('option', { name: '売上' })).toBeInTheDocument()
  expect(screen.getByRole('option', { name: '受注' })).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'CV' })).toBeInTheDocument()
})

it('メトリクス種別が変わると金額欄の単位ヒントが変わる', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('収益・成果を手動で記録')
  // 初期: revenue → '金額（円）'
  expect(screen.getByText('金額（円）')).toBeInTheDocument()

  // combobox ロールは <input list="..."> と <select> 両方が該当するので labelText で絞り込む
  fireEvent.change(screen.getByLabelText('メトリクス'), { target: { value: 'conversions' } })
  expect(screen.getByText('CV件数')).toBeInTheDocument()
})

it('手動フォームの Enter キーで送信できる', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByText('収益・成果を手動で記録')

  fireEvent.change(screen.getByPlaceholderText('組織名'), { target: { value: 'Note Sales' } })
  const amountInput = screen.getByPlaceholderText('0')
  fireEvent.change(amountInput, { target: { value: '3000' } })
  fireEvent.keyDown(amountInput, { key: 'Enter' })

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/outcomes', {
      org_name: 'Note Sales',
      metric: 'revenue',
      value: 3000,
      note: '',
    })
  )
})

// ── inline style 廃止確認（target-input が w-48 クラスを持つ） ──────────────

it('target-input に inline style がなく w-48 クラスを持つ', async () => {
  wireApi()
  renderWithRouter(<RevenuePage />)
  await screen.findByPlaceholderText('月次目標額（円）')
  const input = screen.getByPlaceholderText('月次目標額（円）')
  expect(input.className).toContain('w-48')
  expect(input).not.toHaveAttribute('style')
})

// ── エラー状態 ────────────────────────────────────────────────────────────────

it('API エラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})

// ── スキーマ drift 耐性（null/欠落レスポンスでクラッシュしない） ───────────

it('API が null/欠落レスポンスを返してもクラッシュしない', async () => {
  mockApi.mockImplementation((_method: string, path: string) => {
    if (path === '/api/metrics/revenue') return Promise.resolve(null)
    if (path === '/api/metrics/revenue/report') return Promise.resolve(null)
    if (path === '/api/metrics/revenue/intelligence') return Promise.resolve(null)
    // proposals が null でも Array.isArray ガードで空配列になる
    if (path === '/api/hq/portfolio') return Promise.resolve({ proposals: null })
    return Promise.resolve({})
  })
  renderWithRouter(<RevenuePage />)
  // null レスポンスでもクラッシュせずページが描画される
  // data=null なので KPI は「—」または 0 で表示される（空状態含む）
  expect(await screen.findByText('成果データがありません')).toBeInTheDocument()
})

// ── P14 収益デーモン制御 ──────────────────────────────────────────────────────

describe('P14 収益デーモン制御カード', () => {
  it('カードが描画される', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    expect(await screen.findByText('自律経営（収益デーモン）')).toBeInTheDocument()
  })

  it('daemon 停止中 → 「停止中」バッジを表示する', async () => {
    wireApi({ daemonRunning: false })
    renderWithRouter(<RevenuePage />)
    expect(await screen.findByText('停止中')).toBeInTheDocument()
  })

  it('daemon 稼働中 → 「稼働中」バッジを表示する', async () => {
    wireApi({ daemonRunning: true })
    renderWithRouter(<RevenuePage />)
    expect(await screen.findByText('稼働中')).toBeInTheDocument()
  })

  it('「起動」ボタンで POST /api/daemons/revenue/start を呼ぶ（目標なし）', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('自律経営（収益デーモン）')
    fireEvent.click(screen.getByRole('button', { name: '起動' }))
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/daemons/revenue/start', {})
    )
  })

  it('月次目標を入力して起動すると target を送信する', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('自律経営（収益デーモン）')
    fireEvent.change(screen.getByPlaceholderText('月次目標額（円）任意'), {
      target: { value: '50000' },
    })
    fireEvent.click(screen.getByRole('button', { name: '起動' }))
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/daemons/revenue/start', { target: 50000 })
    )
  })

  it('「停止」ボタンで POST /api/daemons/revenue/stop を呼ぶ', async () => {
    wireApi({ daemonRunning: true })
    renderWithRouter(<RevenuePage />)
    await screen.findByText('自律経営（収益デーモン）')
    fireEvent.click(screen.getByRole('button', { name: '停止' }))
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/daemons/revenue/stop')
    )
  })
})

// ── P22 CSV インポート＋エクスポート ─────────────────────────────────────────

describe('P22 CSV インポート', () => {
  it('インポートカードが描画される', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    expect(await screen.findByText('成果データを一括インポート')).toBeInTheDocument()
  })

  it('CSV テキストを入力してインポートボタンで /api/outcomes/import を呼ぶ', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('成果データを一括インポート')

    const textarea = screen.getByPlaceholderText(/org_name,metric,value,note/)
    fireEvent.change(textarea, {
      target: { value: 'org_name,metric,value\nMy Co,revenue,5000' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'インポート' }))

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith(
        'POST',
        '/api/outcomes/import',
        expect.objectContaining({ rows: expect.any(Array) })
      )
    )
  })

  it('JSON 配列をインポートすると rows にそのまま渡す', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('成果データを一括インポート')

    const jsonInput = JSON.stringify([{ org_name: 'My Co', metric: 'revenue', value: 8000 }])
    const textarea = screen.getByPlaceholderText(/org_name,metric,value,note/)
    fireEvent.change(textarea, { target: { value: jsonInput } })
    fireEvent.click(screen.getByRole('button', { name: 'インポート' }))

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/outcomes/import', {
        rows: [{ org_name: 'My Co', metric: 'revenue', value: 8000 }],
      })
    )
  })
})

describe('P22 CSV エクスポート', () => {
  it('月次データがあるとき「エクスポート (CSV)」ボタンを有効化する', async () => {
    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('月次収益レポート（全組織）')
    const btn = screen.getByRole('button', { name: /エクスポート \(CSV\)/ })
    expect(btn).not.toBeDisabled()
  })

  it('月次データが空のとき「エクスポート (CSV)」ボタンを無効化する', async () => {
    wireApi({ report: emptyReport })
    renderWithRouter(<RevenuePage />)
    await screen.findByText('月次収益レポート（全組織）')
    const btn = screen.getByRole('button', { name: /エクスポート \(CSV\)/ })
    expect(btn).toBeDisabled()
  })

  it('エクスポートボタンクリックで URL.createObjectURL を呼ぶ', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:test')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(globalThis.URL, 'createObjectURL', { value: createObjectURL, writable: true })
    Object.defineProperty(globalThis.URL, 'revokeObjectURL', { value: revokeObjectURL, writable: true })

    wireApi()
    renderWithRouter(<RevenuePage />)
    await screen.findByText('月次収益レポート（全組織）')
    fireEvent.click(screen.getByRole('button', { name: /エクスポート \(CSV\)/ }))
    expect(createObjectURL).toHaveBeenCalled()
  })
})
