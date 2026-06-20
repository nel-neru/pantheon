import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle, DollarSign, Eye, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import type { ObservabilitySummary, ObservabilityTrace } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { formatDateTime, formatNumber } from '@/lib/utils'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function num(x: unknown): number {
  const n = Number(x)
  return Number.isFinite(n) ? n : 0
}

function statusBadge(status: string): string {
  switch (status) {
    case 'ok':
    case 'done':
    case 'success':
      return 'badge-green'
    case 'error':
    case 'failed':
      return 'badge-red'
    case 'running':
      return 'badge-blue'
    default:
      return 'badge-neutral'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'ok':
      return '正常'
    case 'done':
    case 'success':
      return '完了'
    case 'error':
    case 'failed':
      return 'エラー'
    case 'running':
      return '実行中'
    default:
      return status
  }
}

// ─── Sub-component: trace row ─────────────────────────────────────────────────

function TraceRow({ trace }: { trace: ObservabilityTrace }) {
  return (
    <tr>
      <td className="font-mono text-xs text-muted truncate max-w-[8rem]" title={trace.trace_id}>
        {trace.trace_id.slice(0, 8)}…
      </td>
      <td className="font-medium truncate max-w-[12rem]" title={trace.name}>
        {trace.name || '—'}
      </td>
      <td>
        <span className={`badge ${statusBadge(trace.status)}`}>
          {statusLabel(trace.status)}
        </span>
      </td>
      <td className="text-right">{formatNumber(num(trace.span_count))}</td>
      <td className="text-right">
        {trace.elapsed_ms != null && Number.isFinite(Number(trace.elapsed_ms))
          ? `${formatNumber(num(trace.elapsed_ms))} ms`
          : '—'}
      </td>
      <td className="text-right">
        {Number.isFinite(num(trace.total_cost_usd))
          ? `$${num(trace.total_cost_usd).toFixed(5)}`
          : '—'}
      </td>
      <td className="text-right">
        {trace.quality_score != null && Number.isFinite(Number(trace.quality_score))
          ? num(trace.quality_score).toFixed(2)
          : '—'}
      </td>
      <td className="text-xs text-muted">{formatDateTime(trace.started_at)}</td>
    </tr>
  )
}

// ─── Page component ───────────────────────────────────────────────────────────

export function ObservabilityPage() {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<ObservabilitySummary>('GET', '/api/observability/summary')
      setSummary(res ?? null)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'オブザーバビリティデータの読み込みに失敗しました。'
      setSummary(null)
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const traces: ObservabilityTrace[] = summary?.traces ?? []

  return (
    <>
      <PageHeader
        title="オブザーバビリティ"
        subtitle="直近トレースのコスト・品質・レイテンシ集計（読み取り専用）"
        actions={<RefreshButton onClick={() => void load()} busy={loading} />}
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="オブザーバビリティデータを読み込み中…"
          errorTitle="オブザーバビリティデータの読み込みに失敗しました"
        >
          {/* KPI カード */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <Activity size={13} />
                  トレース数
                </div>
                <div className="metric-value">
                  {formatNumber(num(summary?.trace_count))}
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <DollarSign size={13} />
                  合計コスト
                </div>
                <div className="metric-value">
                  ${num(summary?.total_cost_usd).toFixed(4)}
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <CheckCircle size={13} />
                  平均品質
                </div>
                <div className="metric-value">
                  {summary?.avg_quality != null && Number.isFinite(Number(summary.avg_quality))
                    ? num(summary.avg_quality).toFixed(2)
                    : '—'}
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <AlertTriangle size={13} />
                  エラートレース
                </div>
                <div className="metric-value">
                  {formatNumber(num(summary?.error_traces))}
                </div>
              </div>
            </div>
          </div>

          {/* トレース一覧 */}
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2 font-semibold">
                <Zap size={16} />
                トレース一覧（直近 {formatNumber(traces.length)} 件）
              </div>
              {traces.length === 0 ? (
                <div className="empty-state">
                  <Eye className="empty-state-icon" size={28} />
                  <h3>トレースがありません</h3>
                  <p>LLM 呼び出しが実行されるとトレースが記録されます。</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table w-full">
                    <thead>
                      <tr>
                        <th>トレース ID</th>
                        <th>名前</th>
                        <th>状態</th>
                        <th className="text-right">スパン数</th>
                        <th className="text-right">経過時間</th>
                        <th className="text-right">コスト</th>
                        <th className="text-right">品質</th>
                        <th>開始時刻</th>
                      </tr>
                    </thead>
                    <tbody>
                      {traces.map((trace) => (
                        <TraceRow key={trace.trace_id} trace={trace} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </AsyncBoundary>
      </div>
    </>
  )
}
