import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it } from 'vitest'

import { ObservabilityPage } from '../ObservabilityPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const traceA = {
  trace_id: 'trace-aaaaaa-001',
  name: 'improvement_executor',
  task_type: 'improvement',
  pattern: null,
  started_at: '2026-06-20T10:00:00Z',
  span_count: 4,
  elapsed_ms: 3200,
  status: 'ok',
  total_cost_usd: 0.00123,
  input_tokens: 4000,
  output_tokens: 800,
  quality_score: 0.92,
}

const traceB = {
  trace_id: 'trace-bbbbbb-002',
  name: 'code_review',
  task_type: 'review',
  pattern: null,
  started_at: '2026-06-20T09:00:00Z',
  span_count: 2,
  elapsed_ms: 1500,
  status: 'error',
  total_cost_usd: 0.00054,
  input_tokens: 2000,
  output_tokens: 300,
  quality_score: null,
}

const summaryData = {
  trace_count: 2,
  total_cost_usd: 0.00177,
  avg_quality: 0.92,
  error_traces: 1,
  traces: [traceA, traceB],
}

const emptySummary = {
  trace_count: 0,
  total_cost_usd: 0,
  avg_quality: null,
  error_traces: 0,
  traces: [],
}

beforeEach(() => {
  mockApi.mockReset()
})

// ── 基本表示 ──────────────────────────────────────────────────────────────────

it('ページタイトルを表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByText('オブザーバビリティ')).toBeInTheDocument()
})

it('GET /api/observability/summary を呼ぶ', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('オブザーバビリティ')
  expect(mockApi).toHaveBeenCalledWith('GET', '/api/observability/summary')
})

// ── KPI カード ────────────────────────────────────────────────────────────────

it('トレース数ラベルを表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByText('トレース数')).toBeInTheDocument()
})

it('エラートレース数を表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('エラートレース')
  // error_traces: 1
  expect(screen.getByText('エラートレース')).toBeInTheDocument()
})

it('平均品質ラベルを表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByText('平均品質')).toBeInTheDocument()
})

it('avg_quality が null のとき「—」を表示する', async () => {
  mockApi.mockResolvedValue({ ...summaryData, avg_quality: null })
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('平均品質')
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

// ── トレース一覧 ──────────────────────────────────────────────────────────────

it('トレース名を表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByText('improvement_executor')).toBeInTheDocument()
  expect(screen.getByText('code_review')).toBeInTheDocument()
})

it('エラーステータスバッジを表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('improvement_executor')
  expect(screen.getByText('エラー')).toBeInTheDocument()
})

it('正常ステータスバッジを表示する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('improvement_executor')
  expect(screen.getByText('正常')).toBeInTheDocument()
})

// ── 空状態 ────────────────────────────────────────────────────────────────────

it('トレースが0件のとき空状態を表示する', async () => {
  mockApi.mockResolvedValue(emptySummary)
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByText('トレースがありません')).toBeInTheDocument()
})

// ── NaN / null 耐性 ───────────────────────────────────────────────────────────

it('null/欠落フィールドでクラッシュしない（NaN 露出なし）', async () => {
  const nullish = {
    trace_count: null,
    total_cost_usd: null,
    avg_quality: null,
    error_traces: null,
    traces: [
      {
        ...traceA,
        elapsed_ms: null,
        total_cost_usd: null,
        quality_score: null,
        span_count: null,
      },
    ],
  }
  mockApi.mockResolvedValue(nullish)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('improvement_executor')
  expect(document.body.textContent).not.toContain('NaN')
})

// ── エラー / 再試行 ───────────────────────────────────────────────────────────

it('APIエラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('Network error'))
  renderWithRouter(<ObservabilityPage />)
  expect(await screen.findByRole('button', { name: '再試行' })).toBeInTheDocument()
})

it('再試行ボタンで再フェッチする', async () => {
  mockApi.mockRejectedValueOnce(new Error('初回失敗'))
  renderWithRouter(<ObservabilityPage />)
  await screen.findByRole('button', { name: '再試行' })

  mockApi.mockResolvedValue(summaryData)
  await userEvent.click(screen.getByRole('button', { name: '再試行' }))
  expect(await screen.findByText('improvement_executor')).toBeInTheDocument()
})

// ── 更新ボタン ────────────────────────────────────────────────────────────────

it('「更新」ボタンで再取得する', async () => {
  mockApi.mockResolvedValue(summaryData)
  renderWithRouter(<ObservabilityPage />)
  await screen.findByText('improvement_executor')

  const callsBefore = mockApi.mock.calls.length
  await userEvent.click(screen.getByRole('button', { name: '更新' }))

  await waitFor(() => {
    expect(mockApi.mock.calls.length).toBeGreaterThan(callsBefore)
  })
})
