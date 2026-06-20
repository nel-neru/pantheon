import { screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { UsagePage } from '../UsagePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const windowUsageEmpty = {
  window_hours: 5,
  calls: 0,
  input_tokens: 0,
  output_tokens: 0,
  cache_read_tokens: 0,
  total_tokens: 0,
  total_cost_usd: 0,
  measured_calls: 0,
  estimated_calls: 0,
}

const usageData = {
  usage: {
    session_5h: {
      window_hours: 5,
      calls: 12,
      input_tokens: 120000,
      output_tokens: 34000,
      cache_read_tokens: 8000,
      total_tokens: 154000,
      total_cost_usd: 0.4812,
      measured_calls: 10,
      estimated_calls: 2,
    },
    weekly_7d: {
      window_hours: 168,
      calls: 88,
      input_tokens: 900000,
      output_tokens: 260000,
      cache_read_tokens: 45000,
      total_tokens: 1160000,
      total_cost_usd: 3.512,
      measured_calls: 80,
      estimated_calls: 8,
    },
  },
  governor: {
    enabled: true,
    level: 'ok',
    window_hours: 5,
    window_tokens: 154000,
    soft_limit_tokens: 3000000,
    hard_limit_tokens: 5000000,
  },
  rate_limited: false,
  retry_at: null,
  rate_limit_scope: null,
}

const rateLimitedData = {
  ...usageData,
  rate_limited: true,
  retry_at: '2026-06-20T15:30:00Z',
  rate_limit_scope: 'output_tokens',
  governor: { ...usageData.governor, level: 'rate_limited' },
}

const softLimitData = {
  ...usageData,
  governor: { ...usageData.governor, level: 'soft_limit', window_tokens: 3100000 },
}

beforeEach(() => {
  mockApi.mockReset()
})

// ── 基本表示 ──────────────────────────────────────────────────────────────────

it('ページタイトルを表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('使用量')).toBeInTheDocument()
})

it('5h セッション窓カードを表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('直近 5 時間（セッション窓）')).toBeInTheDocument()
})

it('7d 週次窓カードを表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('直近 7 日間（週次窓）')).toBeInTheDocument()
})

it('クォータガバナー状態を表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('クォータガバナー')).toBeInTheDocument()
  expect(screen.getByText('正常')).toBeInTheDocument()
})

it('GET /api/usage/summary を呼ぶ', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')
  expect(mockApi).toHaveBeenCalledWith('GET', '/api/usage/summary')
})

// ── トークン数値の表示 ────────────────────────────────────────────────────────

it('セッション窓のトークン数を表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')
  // 154,000 total tokens (ja-JP format)
  const els = screen.getAllByText('154,000')
  expect(els.length).toBeGreaterThan(0)
})

it('コストを $ で表示する（NaN にならない）', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')
  // $0.4812
  expect(screen.getByText('$0.4812')).toBeInTheDocument()
})

it('実測・推定呼び出し数を表示する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')
  // 実測: 10, 推定: 2
  const measured = screen.getAllByText('10')
  expect(measured.length).toBeGreaterThan(0)
})

// ── レート制限 ────────────────────────────────────────────────────────────────

it('レート制限中は警告カードを表示する', async () => {
  mockApi.mockResolvedValue(rateLimitedData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('レート制限中')).toBeInTheDocument()
})

it('レート制限スコープと再開時刻を表示する', async () => {
  mockApi.mockResolvedValue(rateLimitedData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('レート制限中')
  expect(screen.getByText(/output_tokens/)).toBeInTheDocument()
})

it('レート制限でないとき警告カードを出さない', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('クォータガバナー')
  expect(screen.queryByText('レート制限中')).not.toBeInTheDocument()
})

// ── ガバナーレベル ─────────────────────────────────────────────────────────────

it('ソフト制限中バッジを表示する', async () => {
  mockApi.mockResolvedValue(softLimitData)
  renderWithRouter(<UsagePage />)
  expect(await screen.findByText('ソフト制限中')).toBeInTheDocument()
})

it('ガバナー有効フラグ表示', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('クォータガバナー')
  expect(screen.getByText('有効')).toBeInTheDocument()
})

// ── エラー・再試行 ────────────────────────────────────────────────────────────

it('APIエラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<UsagePage />)
  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})

it('再試行ボタンで再フェッチする', async () => {
  mockApi.mockRejectedValueOnce(new Error('初回失敗'))
  renderWithRouter(<UsagePage />)
  await screen.findByRole('button', { name: '再試行' })

  mockApi.mockResolvedValue(usageData)
  const user = (await import('@testing-library/user-event')).default
  await user.click(screen.getByRole('button', { name: '再試行' }))
  await screen.findByText('直近 5 時間（セッション窓）')
})

// ── null / 欠落ペイロード耐性 ───────────────────────────────────────────────

it('null/欠落フィールドでクラッシュしない（NaN露出なし）', async () => {
  const nullish = {
    usage: {
      session_5h: { ...windowUsageEmpty, total_tokens: null, total_cost_usd: null },
      weekly_7d: { ...windowUsageEmpty },
    },
    governor: {
      enabled: true,
      level: 'ok',
      window_hours: 5,
      window_tokens: null,
      soft_limit_tokens: null,
      hard_limit_tokens: null,
    },
    rate_limited: false,
    retry_at: null,
  }
  mockApi.mockResolvedValue(nullish)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')
  // Should not render any NaN
  expect(document.body.textContent).not.toContain('NaN')
})

it('「更新」ボタンで再取得する', async () => {
  mockApi.mockResolvedValue(usageData)
  renderWithRouter(<UsagePage />)
  await screen.findByText('直近 5 時間（セッション窓）')

  const callsBefore = mockApi.mock.calls.length
  const user = (await import('@testing-library/user-event')).default
  await user.click(screen.getByRole('button', { name: '更新' }))

  await waitFor(() => {
    expect(mockApi.mock.calls.length).toBeGreaterThan(callsBefore)
  })
})
