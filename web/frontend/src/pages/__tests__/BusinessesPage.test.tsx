import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { BusinessesPage } from '../BusinessesPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const bizA = {
  id: 'biz-001',
  name: 'AIコンテンツ事業',
  purpose: '月10万円の収益化',
  member_orgs: ['SNS Growth', 'Note Sales'],
  roles: {},
  handoff_routes: [{ from_org: 'SNS Growth', to_org: 'Note Sales', kind: 'audience_signal' }],
  kpis: ['revenue', 'reach'],
  status: 'active',
  created_at: '2026-06-01T00:00:00Z',
}

const bizB = {
  id: 'biz-002',
  name: 'アフィリエイト事業',
  purpose: '',
  member_orgs: ['Affiliate Revenue'],
  roles: {},
  handoff_routes: [],
  kpis: [],
  status: 'paused',
  created_at: '2026-06-02T00:00:00Z',
}

const outcomes = {
  business: bizA,
  member_orgs: ['SNS Growth', 'Note Sales'],
  by_metric: { revenue: 12000, reach: 5000 },
  event_count: 7,
  total_revenue: 12000,
  total_reach: 5000,
}

function wireApi(overrides?: { businesses?: typeof bizA[] }) {
  const businesses = overrides?.businesses ?? [bizA, bizB]
  mockApi.mockImplementation((_method: string, path: string) => {
    if (path === '/api/businesses') return Promise.resolve({ businesses })
    if (path === '/api/businesses/biz-001/outcomes') return Promise.resolve(outcomes)
    if (path === '/api/businesses/biz-001/compose') return Promise.resolve({ created: 2, handoff_ids: ['h1', 'h2'] })
    if (path === '/api/businesses') return Promise.resolve({ businesses: [] })
    return Promise.resolve({ ok: true, deleted: true })
  })
}

beforeEach(() => {
  mockApi.mockReset()
  mockedToast.error.mockReset()
  mockedToast.success.mockReset()
})

// ── 基本表示 ──────────────────────────────────────────────────────────────────

it('ページタイトルを表示する', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  expect(await screen.findByText('事業')).toBeInTheDocument()
})

it('事業リストを表示する', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  expect(await screen.findByText('AIコンテンツ事業')).toBeInTheDocument()
  expect(screen.getByText('アフィリエイト事業')).toBeInTheDocument()
})

it('ステータスバッジを表示する', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')
  // active → 稼働中
  expect(screen.getByText('稼働中')).toBeInTheDocument()
  // paused → 一時停止中
  expect(screen.getByText('一時停止中')).toBeInTheDocument()
})

it('組織数・ルート数・KPI を表示する', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')
  // bizA has 2 member_orgs, 1 route, 2 kpis
  expect(screen.getByText('月10万円の収益化')).toBeInTheDocument()
  expect(screen.getByText('revenue, reach')).toBeInTheDocument()
})

it('空状態を表示する（事業が0件のとき）', async () => {
  mockApi.mockResolvedValue({ businesses: [] })
  renderWithRouter(<BusinessesPage />)
  expect(await screen.findByText('事業がありません')).toBeInTheDocument()
})

it('APIエラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<BusinessesPage />)
  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})

// ── 作成フォーム ──────────────────────────────────────────────────────────────

it('「事業を作成」ボタンでフォームが開く', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  await userEvent.click(screen.getByRole('button', { name: '事業を作成' }))
  expect(screen.getByText('新規事業を作成')).toBeInTheDocument()
})

it('フォームから POST /api/businesses を呼ぶ', async () => {
  wireApi()
  mockApi.mockImplementation((_method: string, path: string, body?: unknown) => {
    if (_method === 'POST' && path === '/api/businesses') {
      return Promise.resolve({ ...bizA, id: 'biz-new', name: (body as { name: string }).name })
    }
    return Promise.resolve({ businesses: [bizA, bizB] })
  })
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  await userEvent.click(screen.getByRole('button', { name: '事業を作成' }))
  await userEvent.type(screen.getByPlaceholderText('例: AIコンテンツ事業'), '新規テスト事業')
  await userEvent.click(screen.getByRole('button', { name: '作成' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/businesses', expect.objectContaining({
      name: '新規テスト事業',
    }))
  )
})

it('事業名が空のとき作成できない', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  await userEvent.click(screen.getByRole('button', { name: '事業を作成' }))
  await userEvent.click(screen.getByRole('button', { name: '作成' }))

  await waitFor(() =>
    expect(mockedToast.error).toHaveBeenCalledWith('事業名を入力してください。')
  )
})

// ── 成果パネル ────────────────────────────────────────────────────────────────

it('「成果を見る」ボタンで成果パネルを開く', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const buttons = screen.getAllByRole('button', { name: /成果を見る/ })
  await userEvent.click(buttons[0])

  expect(await screen.findByText('成果サマリー')).toBeInTheDocument()
  expect(await screen.findByText('¥12,000')).toBeInTheDocument()
})

it('成果パネルで GET /api/businesses/{id}/outcomes を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const buttons = screen.getAllByRole('button', { name: /成果を見る/ })
  await userEvent.click(buttons[0])

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/businesses/biz-001/outcomes')
  )
})

it('成果パネルを再クリックで閉じる', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const buttons = screen.getAllByRole('button', { name: /成果を見る/ })
  await userEvent.click(buttons[0])
  await screen.findByText('成果サマリー')

  await userEvent.click(buttons[0])
  await waitFor(() => {
    expect(screen.queryByText('成果サマリー')).not.toBeInTheDocument()
  })
})

// ── 実体化（compose）────────────────────────────────────────────────────────

it('「ハンドオフを実体化」ボタンで確認ダイアログを開く', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const composeButtons = screen.getAllByRole('button', { name: /ハンドオフを実体化/ })
  await userEvent.click(composeButtons[0])

  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('実体化を確認すると POST /compose を呼びトーストを出す', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const composeButtons = screen.getAllByRole('button', { name: /ハンドオフを実体化/ })
  await userEvent.click(composeButtons[0])

  const dialog = await screen.findByRole('dialog')
  await userEvent.click(within(dialog).getByRole('button', { name: '実体化する' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/businesses/biz-001/compose')
  )
  await waitFor(() =>
    expect(mockedToast.success).toHaveBeenCalledWith(expect.stringContaining('2 件'))
  )
})

// ── 削除 ──────────────────────────────────────────────────────────────────────

it('「削除」ボタンで確認ダイアログを開く', async () => {
  wireApi()
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const deleteButtons = screen.getAllByRole('button', { name: /削除/ })
  await userEvent.click(deleteButtons[0])

  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('削除を確認すると DELETE /api/businesses/{id} を呼ぶ', async () => {
  wireApi()
  mockApi.mockImplementation((_method: string, path: string) => {
    if (_method === 'DELETE') return Promise.resolve({ ok: true, deleted: true })
    return Promise.resolve({ businesses: [bizB] })
  })
  renderWithRouter(<BusinessesPage />)
  await screen.findByText('AIコンテンツ事業')

  const deleteButtons = screen.getAllByRole('button', { name: /削除/ })
  await userEvent.click(deleteButtons[0])

  const dialog = await screen.findByRole('dialog')
  await userEvent.click(within(dialog).getByRole('button', { name: '削除する' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('DELETE', '/api/businesses/biz-001')
  )
})

// ── null / 欠落ペイロード耐性 ───────────────────────────────────────────────

it('API が null を返してもクラッシュしない', async () => {
  mockApi.mockResolvedValue(null)
  renderWithRouter(<BusinessesPage />)
  // null → businesses = [] → empty state
  expect(await screen.findByText('事業がありません')).toBeInTheDocument()
})
