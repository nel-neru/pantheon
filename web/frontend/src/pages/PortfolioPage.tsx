import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  BarChart2,
  Building2,
  Inbox,
  Layers,
  Star,
  TrendingUp,
} from 'lucide-react'

import { api, type PortfolioOverview } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { formatNumber, formatYen } from '@/lib/utils'

// ─── Label maps ───────────────────────────────────────────────────────────────

/** 推奨アクション (action) の日本語ラベル。 */
const ACTION_LABEL: Record<string, string> = {
  invest: '強化投資',
  monetize: '収益化優先',
  optimize: '効率改善',
  grow_audience: 'リーチ拡大',
}

/** 推奨アクション (action) のバッジ配色。 */
const ACTION_BADGE: Record<string, string> = {
  invest: 'badge-green',
  monetize: 'badge-blue',
  optimize: 'badge-yellow',
  grow_audience: 'badge-neutral',
}

function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action
}

function actionBadge(action: string): string {
  return ACTION_BADGE[action] ?? 'badge-neutral'
}

// ─── Helper: safe numeric coerce ─────────────────────────────────────────────

/** free-form numeric payload を安全に数値化する。非有限値は 0 として扱う。 */
function num(x: unknown): number {
  return Number.isFinite(Number(x)) ? Number(x) : 0
}

// ─── Types ────────────────────────────────────────────────────────────────────

/** ポートフォリオ overview から coerce 済みの 1 org エントリ。 */
type PortfolioOrg = {
  org_name: string
  revenue: number
  reach: number
  roi: number
  revenue_percentile: number
  roi_percentile: number
  action: string
  flag: string
}

/** getPortfolioOverview() の戻り値を coerce した内部表現。 */
type PortfolioState = {
  orgs: PortfolioOrg[]
  org_count: number
  total_revenue: number
  total_reach: number
  pending_handoffs: number
  new_business_candidates: number
}

/** API レスポンスを安全に coerce して PortfolioState を返す。 */
function coerceOverview(raw: PortfolioOverview): PortfolioState {
  return {
    orgs: (Array.isArray(raw?.orgs) ? raw.orgs : []).map((o) => ({
      org_name: String(o?.org_name ?? ''),
      revenue: num(o?.revenue),
      reach: num(o?.reach),
      roi: num(o?.roi),
      revenue_percentile: num(o?.revenue_percentile),
      roi_percentile: num(o?.roi_percentile),
      action: String(o?.action ?? ''),
      flag: String(o?.flag ?? ''),
    })),
    org_count: num(raw?.org_count),
    total_revenue: num(raw?.total_revenue),
    total_reach: num(raw?.total_reach),
    pending_handoffs: num(raw?.pending_handoffs),
    new_business_candidates: num(raw?.new_business_candidates),
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** KPI メトリクスカード（ラベル + 値）。 */
function KpiCard({ icon: Icon, label, value }: { icon: typeof TrendingUp; label: string; value: string }) {
  return (
    <div className="card">
      <div className="card-body">
        <div className="metric-label flex items-center gap-1">
          <Icon size={14} />
          {label}
        </div>
        <div className="metric-value">{value}</div>
      </div>
    </div>
  )
}

// ─── Page component ───────────────────────────────────────────────────────────

export function PortfolioPage() {
  const navigate = useNavigate()

  const [data, setData] = useState<PortfolioState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const raw = await api<PortfolioOverview>('GET', '/api/portfolio/overview')
      setData(coerceOverview(raw))
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'ポートフォリオの読み込みに失敗しました。'
      setData(null)
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const hasOpportunities =
    (data?.pending_handoffs ?? 0) > 0 || (data?.new_business_candidates ?? 0) > 0

  // ROI 降順にソートされた組織リスト（バックエンドも同順に返すが冪等安全のため再ソート）
  const rankedOrgs = data
    ? [...data.orgs].sort((a, b) => b.roi - a.roi)
    : []

  return (
    <>
      <PageHeader
        title="ポートフォリオ司令塔"
        subtitle="ROI 最優先の意思決定サーフェス — 組織ごとの効率・推奨アクションを一望する"
        actions={<RefreshButton onClick={() => void load()} busy={loading} />}
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="ポートフォリオデータを読み込み中…"
          errorTitle="ポートフォリオの読み込みに失敗しました"
        >
          {/* KPI 行 */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4" data-testid="kpi-row">
            <KpiCard
              icon={Building2}
              label="組織数"
              value={String(data?.org_count ?? 0)}
            />
            <KpiCard
              icon={TrendingUp}
              label="累計収益"
              value={formatYen(data?.total_revenue ?? 0)}
            />
            <KpiCard
              icon={BarChart2}
              label="累計リーチ"
              value={formatNumber(data?.total_reach ?? 0)}
            />
            <KpiCard
              icon={AlertTriangle}
              label="引き渡し待ち"
              value={String(data?.pending_handoffs ?? 0)}
            />
            <KpiCard
              icon={Layers}
              label="新規事業候補"
              value={String(data?.new_business_candidates ?? 0)}
            />
          </div>

          {/* 機会コールアウト: pending_handoffs > 0 OR new_business_candidates > 0 */}
          {hasOpportunities ? (
            <div
              className="card border border-yellow-500/30"
              data-testid="opportunity-callout"
            >
              <div className="card-body flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={16} className="text-yellow" />
                  <div className="font-semibold">承認待ちの機会があります</div>
                  <div className="flex items-center gap-2 text-sm text-muted">
                    {(data?.pending_handoffs ?? 0) > 0 ? (
                      <span>引き渡し待ち {data?.pending_handoffs} 件</span>
                    ) : null}
                    {(data?.new_business_candidates ?? 0) > 0 ? (
                      <span>新規事業候補 {data?.new_business_candidates} 件</span>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate('/inbox')}
                  >
                    <Inbox size={14} />
                    承認インボックスを開く
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate('/marketplace')}
                  >
                    <Layers size={14} />
                    マーケットプレイス
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {/* ROI 降順 組織テーブル */}
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Star size={16} />
                <div className="font-semibold">組織別 ROI ランキング</div>
              </div>
              {rankedOrgs.length === 0 ? (
                <div className="text-sm text-muted" data-testid="orgs-empty">
                  組織データがありません。組織を作成して成果を記録すると表示されます。
                </div>
              ) : (
                <table className="data-table" data-testid="org-table">
                  <thead>
                    <tr>
                      <th>組織</th>
                      <th className="text-right">ROI (¥/リーチ)</th>
                      <th className="text-right">収益(¥)</th>
                      <th className="text-right">収益パーセンタイル</th>
                      <th>推奨アクション</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankedOrgs.map((o) => (
                      <tr key={o.org_name} data-testid={`org-row-${o.org_name}`}>
                        <td className="font-medium">
                          <span className="flex items-center gap-1">
                            {o.flag === 'top_performer' ? (
                              <span
                                className="text-yellow-400"
                                title="トップパフォーマー"
                                aria-label="トップパフォーマー"
                              >
                                ★
                              </span>
                            ) : o.flag === 'underperformer' ? (
                              <span
                                className="text-orange-400"
                                title="改善が必要"
                                aria-label="改善が必要"
                              >
                                ⚠
                              </span>
                            ) : null}
                            {o.org_name}
                          </span>
                        </td>
                        <td className="text-right font-mono">
                          {formatYen(Math.round(o.roi * 100) / 100)}
                        </td>
                        <td className="text-right">{formatYen(o.revenue)}</td>
                        <td className="text-right">
                          {Number.isFinite(o.revenue_percentile)
                            ? `${Math.round(o.revenue_percentile)}%`
                            : '—'}
                        </td>
                        <td>
                          <span className={`badge ${actionBadge(o.action)}`}>
                            {actionLabel(o.action)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </AsyncBoundary>
      </div>
    </>
  )
}
