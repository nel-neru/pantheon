import { useState } from 'react'

import { ArrowIcon } from '@/components/Icon'
import { Exhibit, EmptyState, ErrorNote, Loading, Plate, Stat, Tag } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { compactNumber, relativeTime } from '@/lib/format'
import type { ObservabilitySummary, Span, TraceDetail, TraceSummary } from '@/lib/types'

// ステータス → トーンのマッピング（error は rose、ok/success は green、それ以外は neutral）。
const STATUS_TONE: Record<string, 'green' | 'rose' | 'gold' | 'neutral'> = {
  ok: 'green',
  success: 'green',
  completed: 'green',
  error: 'rose',
  failed: 'rose',
  running: 'gold',
  pending: 'gold',
}

function statusTone(status: string): 'green' | 'rose' | 'gold' | 'neutral' {
  return STATUS_TONE[status.toLowerCase()] ?? 'neutral'
}

function fmtCost(usd: number | null): string {
  if (usd === null || usd === undefined) return '—'
  if (usd === 0) return '$0.00'
  if (usd < 0.001) return `$${usd.toFixed(5)}`
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(3)}`
}

function fmtMs(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTokens(input: number | null, output: number | null): string {
  if (input === null && output === null) return '—'
  const i = input ?? 0
  const o = output ?? 0
  return `${compactNumber(i)}↑ ${compactNumber(o)}↓`
}

function fmtQuality(q: number | null): string {
  if (q === null || q === undefined) return '—'
  return q.toFixed(1)
}

// ---- SpanList — トレース内スパン展開 -------------------------------------------

function SpanRow({ span }: { span: Span }) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[color:var(--line)] py-2.5 first:border-t-0">
      <Tag tone={statusTone(span.status)}>{span.status}</Tag>
      <div className="min-w-0 flex-1">
        <span className="mono text-[12px] tracking-wide">{span.name}</span>
        {span.kind ? (
          <span className="ml-2 mono text-faint text-[10px] tracking-wider uppercase">
            {span.kind}
          </span>
        ) : null}
      </div>
      {span.model ? (
        <span className="mono text-faint text-[11px] tracking-wide shrink-0">{span.model}</span>
      ) : null}
      <span className="mono text-faint text-[10px] tracking-wider shrink-0">
        {fmtMs(span.elapsed_ms)}
      </span>
      <span className="mono text-[10px] tracking-wider shrink-0" style={{ color: 'var(--gold)' }}>
        {fmtCost(span.total_cost_usd)}
      </span>
    </li>
  )
}

function SpanList({ traceId }: { traceId: string }) {
  const detail = useApi<TraceDetail>(`/api/observability/traces?trace_id=${traceId}`)

  if (detail.loading) {
    return <Loading label="スパンを取得中" />
  }
  if (detail.error) {
    return (
      <p className="text-dim mono text-[11px] tracking-wide py-3">
        スパン取得エラー: {detail.error}
      </p>
    )
  }
  const spans = detail.data?.spans ?? []
  if (spans.length === 0) {
    return <p className="text-dim text-sm py-3">スパンが見つかりません。</p>
  }
  return (
    <ul>
      {spans.map((span) => (
        <SpanRow key={span.span_id} span={span} />
      ))}
    </ul>
  )
}

// ---- TraceRow — 各トレースの行 --------------------------------------------------

function TraceRow({
  trace,
  expanded,
  onToggle,
}: {
  trace: TraceSummary
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <li>
      <button
        type="button"
        className="w-full text-left border-t border-[color:var(--line)] py-3 first:border-t-0 hover:bg-[color:var(--ink-2)] transition-colors px-0"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <Tag tone={statusTone(trace.status)}>{trace.status}</Tag>
          <div className="min-w-0 flex-1">
            <div className="truncate mono text-[12px] tracking-wide">{trace.name}</div>
            <div className="flex flex-wrap items-center gap-x-3 mt-0.5">
              {trace.task_type ? (
                <span className="mono text-faint text-[10px] tracking-wider">
                  {trace.task_type}
                </span>
              ) : null}
              {trace.pattern ? (
                <span className="mono text-faint text-[10px] tracking-wider">{trace.pattern}</span>
              ) : null}
              <span className="mono text-faint text-[10px] tracking-wider">
                {relativeTime(trace.started_at)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4 shrink-0">
            <span className="mono text-faint text-[10px] tracking-wider">
              {fmtTokens(trace.input_tokens, trace.output_tokens)}
            </span>
            <span
              className="mono text-[11px] tracking-wider"
              style={{ color: 'var(--gold)' }}
            >
              {fmtCost(trace.total_cost_usd)}
            </span>
            <span className="mono text-faint text-[10px] tracking-wider">
              Q {fmtQuality(trace.quality_score)}
            </span>
            <span className="mono text-faint text-[10px] tracking-wider">
              {fmtMs(trace.elapsed_ms)}
            </span>
            <span
              className="transition-transform"
              style={{
                display: 'inline-flex',
                transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
              }}
            >
              <ArrowIcon size={13} />
            </span>
          </div>
        </div>
      </button>
      {expanded ? (
        <div className="pl-4 pb-3 border-l-2 border-[color:var(--line)] ml-2 mt-1">
          <div className="mono text-[10px] tracking-[0.18em] uppercase text-faint mb-2">
            Spans · {trace.span_count}
          </div>
          <SpanList traceId={trace.trace_id} />
        </div>
      ) : null}
    </li>
  )
}

// ---- Header -------------------------------------------------------------------

function Header() {
  return (
    <Exhibit
      index={6}
      kicker="The Lab"
      title={
        <>
          軌跡を、
          <br />
          <em>解剖する。</em>
        </>
      }
      lede="エージェントが歩んだすべての軌跡がここに集まります。トレース・スパン・コスト・品質スコアを一覧し、生成パイプラインの内側を観測してください。"
    />
  )
}

// ---- Lab page -----------------------------------------------------------------

export function Lab() {
  const summary = useApi<ObservabilitySummary>('/api/observability/summary?limit=20', 30000)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id))

  if (summary.loading && !summary.data) {
    return (
      <>
        <Header />
        <Loading label="トレースを観測中" />
      </>
    )
  }
  if (summary.error && !summary.data) {
    return (
      <>
        <Header />
        <ErrorNote message={summary.error} />
      </>
    )
  }

  const data = summary.data
  const traces = data?.traces ?? []

  const avgQualityDisplay =
    data?.avg_quality !== null && data?.avg_quality !== undefined
      ? data.avg_quality.toFixed(2)
      : '—'

  return (
    <>
      <Header />

      {/* Inline SVG — ラボの特徴的な装飾：波線グラフのイメージ */}
      <div aria-hidden="true" className="my-8">
        <svg
          width="100%"
          height="32"
          viewBox="0 0 600 32"
          preserveAspectRatio="none"
          fill="none"
          stroke="var(--line)"
          strokeWidth="1"
        >
          {/* hand-drawn style trace line */}
          <polyline
            points="0,24 40,20 80,26 120,16 160,22 200,12 240,20 280,8 320,18 360,10 400,22 440,14 480,20 520,16 560,22 600,18"
            strokeDasharray="4 3"
          />
          <circle cx="280" cy="8" r="3" fill="var(--gold)" stroke="none" />
        </svg>
      </div>

      {/* Headline stats */}
      <section className="mt-4 grid grid-cols-2 gap-y-10 gap-x-6 md:grid-cols-4">
        <Stat
          label="Traces"
          value={data?.trace_count ?? 0}
          tone="gold"
          sub="観測済みトレース"
        />
        <Stat
          label="Total Cost"
          value={fmtCost(data?.total_cost_usd ?? null)}
          tone="plain"
          sub="累計コスト (USD)"
        />
        <Stat
          label="Avg Quality"
          value={avgQualityDisplay}
          tone="ice"
          sub="平均品質スコア"
        />
        <Stat
          label="Errors"
          value={data?.error_traces ?? 0}
          tone={data?.error_traces ? 'plain' : 'gold'}
          sub="エラートレース数"
        />
      </section>

      {/* Recent traces table */}
      <section className="mt-14">
        <Plate no="PL. 01" className="rise">
          <div className="mb-5 flex items-baseline justify-between">
            <h2 className="serif text-2xl">Recent Traces</h2>
            <span className="kicker">最新 {traces.length} 件</span>
          </div>

          {traces.length === 0 ? (
            <EmptyState
              title="まだトレースがありません"
              hint="エージェントが実行されると、ここにトレースが記録されます。"
            />
          ) : (
            <ul>
              {traces.map((trace) => (
                <TraceRow
                  key={trace.trace_id}
                  trace={trace}
                  expanded={expandedId === trace.trace_id}
                  onToggle={() => toggle(trace.trace_id)}
                />
              ))}
            </ul>
          )}
        </Plate>
      </section>

      {/* Token legend */}
      <p className="mt-6 mono text-faint text-[10px] tracking-wider">
        ↑ = input tokens &nbsp;·&nbsp; ↓ = output tokens &nbsp;·&nbsp; Q = quality score
        &nbsp;·&nbsp; クリックでスパンを展開
      </p>
    </>
  )
}
