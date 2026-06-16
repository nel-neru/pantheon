import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Lab } from '../Lab'
import type { ObservabilitySummary, TraceDetail } from '@/lib/types'

// ---- fixtures ----------------------------------------------------------------

const traceA = {
  trace_id: 'tr-001',
  name: 'code_review_run',
  task_type: 'review',
  pattern: 'single_agent',
  started_at: '2026-06-17T10:00:00Z',
  span_count: 3,
  elapsed_ms: 4200,
  status: 'ok',
  total_cost_usd: 0.0042,
  input_tokens: 1200,
  output_tokens: 800,
  quality_score: 8.5,
}

const traceB = {
  trace_id: 'tr-002',
  name: 'improvement_apply',
  task_type: 'improvement',
  pattern: null,
  started_at: '2026-06-17T09:30:00Z',
  span_count: 5,
  elapsed_ms: 12000,
  status: 'error',
  total_cost_usd: 0.012,
  input_tokens: 2000,
  output_tokens: 1500,
  quality_score: null,
}

const summaryPayload: ObservabilitySummary = {
  trace_count: 2,
  total_cost_usd: 0.0162,
  avg_quality: 8.5,
  error_traces: 1,
  traces: [traceA, traceB],
}

const detailPayload: TraceDetail = {
  trace_id: 'tr-001',
  spans: [
    {
      span_id: 'sp-1',
      trace_id: 'tr-001',
      parent_span_id: null,
      kind: 'llm',
      name: 'claude_call',
      task_type: 'review',
      pattern: null,
      elapsed_ms: 3100,
      status: 'ok',
      model: 'claude-sonnet',
      total_cost_usd: 0.003,
      quality_score: 8.5,
    },
    {
      span_id: 'sp-2',
      trace_id: 'tr-001',
      parent_span_id: 'sp-1',
      kind: 'tool',
      name: 'read_file',
      task_type: null,
      pattern: null,
      elapsed_ms: 50,
      status: 'ok',
      model: null,
      total_cost_usd: null,
      quality_score: null,
    },
  ],
}

// ---- mock helpers ------------------------------------------------------------

function mockFetch(overrideSummary?: ObservabilitySummary | null) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/observability/summary')) {
      if (overrideSummary === null) {
        return { ok: false, status: 503, json: async () => ({ detail: 'backend down' }) }
      }
      return { ok: true, json: async () => (overrideSummary ?? summaryPayload) }
    }
    if (url.includes('/api/observability/traces')) {
      return { ok: true, json: async () => detailPayload }
    }
    return { ok: true, json: async () => [] }
  }) as unknown as typeof fetch
}

// ---- tests -------------------------------------------------------------------

describe('Lab page', () => {
  beforeEach(() => {
    mockFetch()
  })

  it('renders the exhibition header kicker', () => {
    render(<Lab />)
    expect(screen.getByText('The Lab')).toBeInTheDocument()
  })

  it('displays headline stats once data loads', async () => {
    render(<Lab />)

    await waitFor(() => {
      expect(screen.getByText('Traces')).toBeInTheDocument()
    })

    // trace_count=2 is unique on the page
    expect(screen.getByText('2')).toBeInTheDocument()
    // error_traces=1 — rendered under "Errors" stat
    expect(screen.getByText('Errors')).toBeInTheDocument()
    // avg_quality=8.5 → "8.50"
    expect(screen.getByText('8.50')).toBeInTheDocument()
  })

  it('renders a trace row with name and status tag', async () => {
    render(<Lab />)

    await waitFor(() => {
      expect(screen.getByText('code_review_run')).toBeInTheDocument()
    })

    // Status tag for the first trace
    expect(screen.getAllByText('ok').length).toBeGreaterThanOrEqual(1)
    // Second trace name
    expect(screen.getByText('improvement_apply')).toBeInTheDocument()
    // Error status on second trace
    expect(screen.getAllByText('error').length).toBeGreaterThanOrEqual(1)
  })

  it('drill-down: clicking a trace row fetches spans and renders them', async () => {
    const user = userEvent.setup()
    render(<Lab />)

    // Wait for trace rows to appear
    await waitFor(() => {
      expect(screen.getByText('code_review_run')).toBeInTheDocument()
    })

    // Click the first trace row button
    const firstRow = screen.getByRole('button', { name: /code_review_run/i })
    await user.click(firstRow)

    // Span detail should now load — check span name "claude_call"
    await waitFor(() => {
      expect(screen.getByText('claude_call')).toBeInTheDocument()
    })
    expect(screen.getByText('read_file')).toBeInTheDocument()
    // Model label rendered
    expect(screen.getByText('claude-sonnet')).toBeInTheDocument()
  })

  it('collapsing the expanded row hides span detail', async () => {
    const user = userEvent.setup()
    render(<Lab />)

    await waitFor(() => expect(screen.getByText('code_review_run')).toBeInTheDocument())

    const firstRow = screen.getByRole('button', { name: /code_review_run/i })
    // expand
    await user.click(firstRow)
    await waitFor(() => expect(screen.getByText('claude_call')).toBeInTheDocument())

    // collapse
    await user.click(firstRow)
    await waitFor(() => {
      expect(screen.queryByText('claude_call')).not.toBeInTheDocument()
    })
  })

  it('shows error state when summary endpoint fails', async () => {
    mockFetch(null)
    render(<Lab />)

    await waitFor(() => {
      expect(screen.getByText('接続エラー')).toBeInTheDocument()
    })
  })

  it('shows empty state when there are no traces', async () => {
    mockFetch({
      ...summaryPayload,
      trace_count: 0,
      traces: [],
    })
    render(<Lab />)

    await waitFor(() => {
      expect(screen.getByText('まだトレースがありません')).toBeInTheDocument()
    })
  })
})
