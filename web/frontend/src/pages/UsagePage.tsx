import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, Cpu, TrendingUp, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { formatDateTime, formatNumber } from '@/lib/utils'

// ─── Types ───────────────────────────────────────────────────────────────────

type WindowUsage = {
  window_hours: number
  calls: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  total_tokens: number
  total_cost_usd: number
  measured_calls: number
  estimated_calls: number
}

type UsageSummary = {
  session_5h: WindowUsage
  weekly_7d: WindowUsage
}

type GovernorStatus = {
  enabled: boolean
  level: string
  window_hours: number
  window_tokens: number
  soft_limit_tokens: number
  hard_limit_tokens: number
}

type UsageData = {
  usage: UsageSummary
  governor: GovernorStatus
  rate_limited: boolean
  retry_at?: string | null
  rate_limit_scope?: string | null
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function num(x: unknown): number {
  const n = Number(x)
  return Number.isFinite(n) ? n : 0
}

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0
  const p = (used / limit) * 100
  return Math.min(100, Number.isFinite(p) ? p : 0)
}

function governorLevelLabel(level: string): string {
  switch (level) {
    case 'ok':
      return '正常'
    case 'soft_limit':
      return 'ソフト制限中'
    case 'hard_limit':
      return 'ハード制限中'
    case 'rate_limited':
      return 'レート制限中'
    default:
      return level
  }
}

function governorLevelBadge(level: string): string {
  switch (level) {
    case 'ok':
      return 'badge-green'
    case 'soft_limit':
      return 'badge-yellow'
    case 'hard_limit':
    case 'rate_limited':
      return 'badge-red'
    default:
      return 'badge-neutral'
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function WindowCard({ label, usage }: { label: string; usage: WindowUsage }) {
  const totalTokens = num(usage.total_tokens)
  const inputTokens = num(usage.input_tokens)
  const outputTokens = num(usage.output_tokens)
  const cacheTokens = num(usage.cache_read_tokens)
  const calls = num(usage.calls)
  const costUsd = num(usage.total_cost_usd)
  const measuredCalls = num(usage.measured_calls)
  const estimatedCalls = num(usage.estimated_calls)

  return (
    <div className="card">
      <div className="card-body flex flex-col gap-3">
        <div className="flex items-center gap-2 font-semibold">
          <TrendingUp size={16} />
          {label}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <div className="metric-label">合計トークン</div>
            <div className="text-lg font-bold">{formatNumber(totalTokens)}</div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="metric-label flex items-center gap-1">
              <Cpu size={12} />
              入力トークン
            </div>
            <div className="text-lg font-bold">{formatNumber(inputTokens)}</div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="metric-label">出力トークン</div>
            <div className="text-lg font-bold">{formatNumber(outputTokens)}</div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="metric-label">キャッシュ読み取り</div>
            <div className="text-lg font-bold">{formatNumber(cacheTokens)}</div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="metric-label flex items-center gap-1">
              <Activity size={12} />
              呼び出し回数
            </div>
            <div className="text-lg font-bold">{formatNumber(calls)}</div>
          </div>
          <div className="flex flex-col gap-1">
            <div className="metric-label">推定コスト</div>
            <div className="text-lg font-bold">
              ${costUsd.toFixed(4)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
          <span>
            実測: <span className="font-medium text-fg">{formatNumber(measuredCalls)}</span> 回
          </span>
          <span>
            推定（旧CLI）: <span className="font-medium text-fg">{formatNumber(estimatedCalls)}</span> 回
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── Page component ───────────────────────────────────────────────────────────

export function UsagePage() {
  const [data, setData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<UsageData>('GET', '/api/usage/summary')
      setData(res ?? null)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '使用量の読み込みに失敗しました。'
      setData(null)
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const governor = data?.governor
  const rateLimited = Boolean(data?.rate_limited)
  const retryAt = data?.retry_at ?? null
  const rateLimitScope = data?.rate_limit_scope ?? null

  const windowTokens = num(governor?.window_tokens)
  const softLimit = num(governor?.soft_limit_tokens)
  const hardLimit = num(governor?.hard_limit_tokens)
  const softPct = pct(windowTokens, softLimit)
  const hardPct = pct(windowTokens, hardLimit)

  return (
    <>
      <PageHeader
        title="使用量"
        subtitle="トークン消費 / クォータガバナー / レート制限の現況（自律運営コスト）"
        actions={<RefreshButton onClick={() => void load()} busy={loading} />}
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="使用量を読み込み中…"
          errorTitle="使用量の読み込みに失敗しました"
        >
          {/* Rate-limit alert */}
          {rateLimited && (
            <div className="card">
              <div className="card-body flex items-start gap-3">
                <AlertTriangle size={18} className="text-yellow shrink-0 mt-0.5" />
                <div className="flex flex-col gap-1">
                  <div className="font-semibold">レート制限中</div>
                  <div className="text-sm text-muted">
                    {rateLimitScope ? `スコープ: ${rateLimitScope}` : null}
                    {retryAt ? (
                      <>
                        {rateLimitScope ? ' — ' : null}
                        再開予定:{' '}
                        <span className="font-medium text-fg">{formatDateTime(retryAt)}</span>
                      </>
                    ) : null}
                    {!rateLimitScope && !retryAt ? 'レート制限中です。しばらくお待ちください。' : null}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Quota governor status */}
          {governor && (
            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2 font-semibold">
                    <Zap size={16} />
                    クォータガバナー
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`badge ${governorLevelBadge(governor.level ?? '')}`}
                    >
                      {governorLevelLabel(governor.level ?? '')}
                    </span>
                    {governor.enabled ? (
                      <span className="flex items-center gap-1 text-sm text-muted">
                        <CheckCircle size={13} className="text-green-500" />
                        有効
                      </span>
                    ) : (
                      <span className="text-sm text-muted">無効</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex justify-between text-sm text-muted">
                    <span>
                      窓内トークン: <span className="font-medium text-fg">{formatNumber(windowTokens)}</span>
                    </span>
                    <span>
                      ハード上限: <span className="font-medium text-fg">{formatNumber(hardLimit)}</span>
                    </span>
                  </div>

                  {/* Progress bar — vs hard limit */}
                  <div
                    className="relative h-3 rounded-full bg-white/10 overflow-hidden"
                    title={`${hardPct.toFixed(1)}% of hard limit`}
                  >
                    {/* soft limit marker */}
                    {softLimit > 0 && hardLimit > 0 && (
                      <div
                        className="absolute top-0 bottom-0 w-px bg-yellow-400/60"
                        style={{ left: `${pct(softLimit, hardLimit)}%` }}
                        title={`ソフト上限: ${formatNumber(softLimit)}`}
                      />
                    )}
                    <div
                      className={`h-full rounded-full transition-all ${
                        hardPct >= 100
                          ? 'bg-red-500'
                          : hardPct >= softPct && windowTokens >= softLimit
                            ? 'bg-yellow-400'
                            : 'bg-blue-500'
                      }`}
                      style={{ width: `${hardPct}%` }}
                    />
                  </div>

                  <div className="flex justify-between text-xs text-muted">
                    <span>0</span>
                    <span>
                      ソフト上限: {formatNumber(softLimit)} ({softPct.toFixed(0)}%)
                    </span>
                    <span>{formatNumber(hardLimit)}</span>
                  </div>
                </div>

                <div className="text-sm text-muted flex items-center gap-1">
                  <Clock size={13} />
                  集計窓: <span className="font-medium text-fg ml-1">{num(governor.window_hours)} 時間</span>
                </div>
              </div>
            </div>
          )}

          {/* Token usage windows */}
          {data?.usage && (
            <>
              <WindowCard label="直近 5 時間（セッション窓）" usage={data.usage.session_5h} />
              <WindowCard label="直近 7 日間（週次窓）" usage={data.usage.weekly_7d} />
            </>
          )}
        </AsyncBoundary>
      </div>
    </>
  )
}
