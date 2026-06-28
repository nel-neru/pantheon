import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it } from 'vitest'

import { UiStatusPage } from '../UiStatusPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const reportData = {
  generated_at: '2026-06-25T10:00:00Z',
  overall: {
    pages: 2,
    ok: 1,
    degraded: 0,
    error: 1,
    total_apis: 3,
    ok_apis: 2,
  },
  pages: [
    {
      route: '/dashboard',
      label: 'ダッシュボード',
      group: 'はじめに',
      status: 'ok',
      static: false,
      apis: [
        {
          method: 'GET',
          path: '/api/platform/status',
          status_code: 200,
          ok: true,
          latency_ms: 12,
          error: null,
        },
      ],
      controls: ['初期化ボタン'],
    },
    {
      route: '/revenue',
      label: '収益',
      group: '収益化',
      status: 'error',
      static: false,
      apis: [
        {
          method: 'GET',
          path: '/api/metrics/revenue/integrity',
          status_code: 500,
          ok: false,
          latency_ms: 8,
          error: 'Internal Server Error',
        },
      ],
      controls: [],
    },
  ],
}

const unavailable = {
  available: false,
  message: 'まだチェックが実行されていません。',
}

beforeEach(() => {
  mockApi.mockReset()
})

// ── (a) レポート描画: ページ行 + status バッジ ───────────────────────────────

it('レポートの各ページ行を描画する', async () => {
  mockApi.mockResolvedValue(reportData)
  renderWithRouter(<UiStatusPage />)
  expect(await screen.findByText('ダッシュボード')).toBeInTheDocument()
  expect(screen.getByText('収益')).toBeInTheDocument()
  // ルートも描画される
  expect(screen.getByText('/dashboard')).toBeInTheDocument()
  expect(screen.getByText('/revenue')).toBeInTheDocument()
})

it('status バッジ（正常 / エラー）を描画する', async () => {
  mockApi.mockResolvedValue(reportData)
  renderWithRouter(<UiStatusPage />)
  await screen.findByText('ダッシュボード')
  // 「正常」「エラー」はサマリ KPI ラベルとも重複するため、バッジ配色で絞り込んで検証する。
  const okBadge = screen.getAllByText('正常').find((el) => el.classList.contains('badge-green'))
  const errorBadge = screen.getAllByText('エラー').find((el) => el.classList.contains('badge-red'))
  expect(okBadge).toBeDefined()
  expect(errorBadge).toBeDefined()
})

it('GET /api/ui/status を呼ぶ', async () => {
  mockApi.mockResolvedValue(reportData)
  renderWithRouter(<UiStatusPage />)
  await screen.findByText('ダッシュボード')
  expect(mockApi).toHaveBeenCalledWith('GET', '/api/ui/status')
})

it('null/欠落フィールドでも NaN を露出しない', async () => {
  mockApi.mockResolvedValue({
    generated_at: '2026-06-25T10:00:00Z',
    overall: {
      pages: null,
      ok: null,
      degraded: null,
      error: null,
      total_apis: null,
      ok_apis: null,
    },
    pages: [
      {
        ...reportData.pages[0],
        apis: [{ ...reportData.pages[0].apis[0], latency_ms: null, status_code: null }],
      },
    ],
  })
  renderWithRouter(<UiStatusPage />)
  await screen.findByText('ダッシュボード')
  expect(document.body.textContent).not.toContain('NaN')
})

// ── (b) available:false で空状態 + 再チェックボタン ──────────────────────────

it('available:false のとき未生成の空状態と再チェックボタンを表示する', async () => {
  mockApi.mockResolvedValue(unavailable)
  renderWithRouter(<UiStatusPage />)
  expect(await screen.findByText('未生成')).toBeInTheDocument()
  expect(screen.getByText('まだチェックが実行されていません。')).toBeInTheDocument()
  // 空状態内の再チェックボタン（+ ヘッダの再チェックボタン）
  expect(screen.getAllByRole('button', { name: '再チェック' }).length).toBeGreaterThan(0)
})

// ── (c) 再チェック押下で refreshUiStatus（POST /api/ui/status/refresh）が呼ばれる ─

it('再チェック押下で POST /api/ui/status/refresh を呼ぶ', async () => {
  mockApi.mockResolvedValue(unavailable)
  renderWithRouter(<UiStatusPage />)
  await screen.findByText('未生成')

  mockApi.mockResolvedValue(reportData)
  // ヘッダの再チェックボタンを押す（最初の一致でよい）
  const buttons = screen.getAllByRole('button', { name: '再チェック' })
  await userEvent.click(buttons[0])

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/ui/status/refresh')
  })
  // 再チェック結果が反映され、ページ行が現れる
  expect(await screen.findByText('ダッシュボード')).toBeInTheDocument()
})

// ── エラー / 再試行 ───────────────────────────────────────────────────────────

it('API エラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<UiStatusPage />)
  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})
