import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CalendarDays,
  Coins,
  Eye,
  Plus,
  RefreshCw,
  Send,
  Target,
  TrendingUp,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type RevenueOrg = {
  org_name: string
  reach: number
  revenue: number
  posts: number
  reach_but_no_revenue: boolean
}

type RevenueMetrics = {
  orgs: RevenueOrg[]
  total_revenue: number
  total_reach: number
}

type RevenueReport = {
  by_month: Record<string, number>
  total_revenue: number
}

type RevenueIntelligence = {
  trend: 'growing' | 'flat' | 'declining' | 'insufficient'
  latest_change_pct: number | null
  forecast_next: number
}

type PortfolioProposal = {
  kind: string
  title: string
  reason: string
  priority: number
}

const REVENUE_METRICS = ['revenue', 'sales', 'conversions'] as const
type RevenueMetric = (typeof REVENUE_METRICS)[number]

const TREND_LABEL: Record<RevenueIntelligence['trend'], string> = {
  growing: '成長',
  flat: '横ばい',
  declining: '逓減',
  insufficient: 'データ不足',
}
const TREND_BADGE: Record<RevenueIntelligence['trend'], string> = {
  growing: 'badge-green',
  flat: 'badge-neutral',
  declining: 'badge-yellow',
  insufficient: 'badge-neutral',
}

function fmt(n: number): string {
  return Math.round(n).toLocaleString('ja-JP')
}

export function RevenuePage() {
  const navigate = useNavigate()
  const [data, setData] = useState<RevenueMetrics | null>(null)
  const [report, setReport] = useState<RevenueReport | null>(null)
  const [intel, setIntel] = useState<RevenueIntelligence | null>(null)
  const [portfolio, setPortfolio] = useState<PortfolioProposal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 手動入力フォーム
  const [formOrg, setFormOrg] = useState('')
  const [formMetric, setFormMetric] = useState<RevenueMetric>('revenue')
  const [formValue, setFormValue] = useState('')
  const [formNote, setFormNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // P4.1 自律経営プラン（目標額）
  const [targetInput, setTargetInput] = useState('')
  const [planning, setPlanning] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [result, rep, ai, pf] = await Promise.all([
        api<RevenueMetrics>('GET', '/api/metrics/revenue'),
        api<RevenueReport>('GET', '/api/metrics/revenue/report'),
        api<RevenueIntelligence>('GET', '/api/metrics/revenue/intelligence'),
        api<{ proposals: PortfolioProposal[] }>('GET', '/api/hq/portfolio'),
      ])
      setData(result)
      setReport(rep)
      setIntel(ai)
      setPortfolio(pf.proposals)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '収益メトリクスの読み込みに失敗しました。'
      setData(null)
      setReport(null)
      setIntel(null)
      setPortfolio([])
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const submitOutcome = useCallback(async () => {
    const org = formOrg.trim()
    const value = Number(formValue)
    if (!org) {
      toast.error('組織名を入力してください。')
      return
    }
    if (!formValue.trim() || Number.isNaN(value)) {
      toast.error('金額（数値）を入力してください。')
      return
    }
    setSubmitting(true)
    try {
      await api('POST', '/api/outcomes', {
        org_name: org,
        metric: formMetric,
        value,
        note: formNote.trim(),
      })
      toast.success(`${org} に ${formMetric} ${fmt(value)} を記録しました。`)
      setFormValue('')
      setFormNote('')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '記録に失敗しました。')
    } finally {
      setSubmitting(false)
    }
  }, [formOrg, formMetric, formValue, formNote, load])

  const runTargetPlan = useCallback(async () => {
    const target = Number(targetInput)
    if (!targetInput.trim() || Number.isNaN(target) || target <= 0) {
      toast.error('月次目標額（正の数値）を入力してください。')
      return
    }
    setPlanning(true)
    try {
      const res = await api<{ proposals: number; reason?: string }>(
        'POST',
        '/api/hq/portfolio/scan',
        { target }
      )
      if (res.reason === 'no_org') {
        toast.error('受け手の組織がありません。先に会社を作成してください。')
      } else {
        toast.success(`月${fmt(target)}円目標のプランを ${res.proposals} 件、承認キューに起票しました。`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'プラン生成に失敗しました。')
    } finally {
      setPlanning(false)
    }
  }, [targetInput])

  const orgs = data?.orgs ?? []
  const alerts = orgs.filter((o) => o.reach_but_no_revenue)
  const months = report ? Object.entries(report.by_month) : []

  return (
    <>
      <header className="page-header">
        <div className="page-title">収益ダッシュボード</div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">収益メトリクスを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>収益メトリクスの読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && data ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <Coins size={14} />
                    累計収益
                  </div>
                  <div className="metric-value">¥{fmt(data.total_revenue)}</div>
                </div>
              </div>
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <TrendingUp size={14} />
                    累計リーチ
                  </div>
                  <div className="metric-value">{fmt(data.total_reach)}</div>
                </div>
              </div>
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <Send size={14} />
                    投稿実績（全組織）
                  </div>
                  <div className="metric-value">{fmt(orgs.reduce((sum, o) => sum + o.posts, 0))}</div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Plus size={16} />
                  <div className="font-semibold">収益・成果を手動で記録</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-muted">組織</span>
                    <input
                      className="input"
                      list="revenue-org-options"
                      placeholder="組織名"
                      value={formOrg}
                      onChange={(e) => setFormOrg(e.target.value)}
                    />
                    <datalist id="revenue-org-options">
                      {orgs.map((o) => (
                        <option key={o.org_name} value={o.org_name} />
                      ))}
                    </datalist>
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-muted">メトリクス</span>
                    <select
                      className="select"
                      value={formMetric}
                      onChange={(e) => setFormMetric(e.target.value as RevenueMetric)}
                    >
                      {REVENUE_METRICS.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-muted">金額 / 件数</span>
                    <input
                      className="input"
                      type="number"
                      inputMode="numeric"
                      placeholder="0"
                      value={formValue}
                      onChange={(e) => setFormValue(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={submitting}
                    onClick={() => void submitOutcome()}
                  >
                    <Plus size={14} />
                    記録
                  </button>
                </div>
                <input
                  className="input"
                  placeholder="メモ（任意）"
                  value={formNote}
                  onChange={(e) => setFormNote(e.target.value)}
                />
              </div>
            </div>

            {intel && intel.trend !== 'insufficient' ? (
              <div className="card">
                <div className="card-body flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} />
                    <div className="font-semibold">収益トレンド（全組織）</div>
                    <span className={`badge ${TREND_BADGE[intel.trend]}`}>{TREND_LABEL[intel.trend]}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    {intel.latest_change_pct !== null ? (
                      <span className="text-muted">
                        前月比 <span className="font-medium">{intel.latest_change_pct > 0 ? '+' : ''}{intel.latest_change_pct}%</span>
                      </span>
                    ) : null}
                    <span className="text-muted">
                      翌月予測 <span className="font-medium">¥{fmt(intel.forecast_next)}</span>
                    </span>
                  </div>
                </div>
              </div>
            ) : null}

            {portfolio.length > 0 ? (
              <div className="card">
                <div className="card-body flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} />
                    <div className="font-semibold">ポートフォリオ提案（HQ）</div>
                  </div>
                  <p className="text-muted text-sm">
                    各組織の収益/リーチから「投資・収益化・送客」の打ち手を提案します。
                  </p>
                  {portfolio.map((p, i) => (
                    <div key={`${p.kind}-${i}`} className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="min-w-0">
                        <div className="font-medium truncate">{p.title}</div>
                        <div className="text-sm text-muted">{p.reason}</div>
                      </div>
                      <span className="badge badge-neutral">{p.kind}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Target size={16} />
                  <div className="font-semibold">自律経営プラン（月収益目標）</div>
                </div>
                <p className="text-muted text-sm">
                  「月XX円で最適運用して」を 1 クリックで。目標とのギャップから配分・送客・
                  （リーチ不足なら）新規事業の打ち手を承認キューに起票します（自動実行はしません）。
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    className="input"
                    style={{ width: '12rem' }}
                    type="number"
                    min={0}
                    placeholder="月次目標額（円）"
                    value={targetInput}
                    onChange={(e) => setTargetInput(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={planning}
                    onClick={() => void runTargetPlan()}
                  >
                    <Target size={14} />
                    {planning ? 'プラン生成中…' : 'プランを起票'}
                  </button>
                </div>
              </div>
            </div>

            {months.length > 0 ? (
              <div className="card">
                <div className="card-body flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <CalendarDays size={16} />
                    <div className="font-semibold">月次収益レポート（全組織）</div>
                  </div>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>月</th>
                        <th className="text-right">収益(¥)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {months.map(([month, total]) => (
                        <tr key={month}>
                          <td className="font-medium">{month}</td>
                          <td className="text-right">¥{fmt(total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {alerts.length > 0 ? (
              <div className="card">
                <div className="card-body flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={16} className="text-yellow" />
                    <div className="font-semibold">リーチはあるが収益0の組織（収益化の余地）</div>
                  </div>
                  {alerts.map((o) => (
                    <div key={o.org_name} className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="text-sm">
                        <span className="font-medium">{o.org_name}</span>
                        <span className="text-muted"> ・ リーチ {fmt(o.reach)} / 収益 ¥0</span>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => navigate('/handoffs')}
                      >
                        <Eye size={14} />
                        収益化の引き渡しを確認
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="card">
              <div className="card-body">
                {orgs.length === 0 ? (
                  <div className="empty-state">
                    <Coins className="empty-state-icon" size={28} />
                    <h3>成果データがありません</h3>
                    <p>
                      投稿が公開され、`pantheon hq outcomes` で reach / revenue を記録すると、ここに
                      組織別の収益とリーチが集計されます。
                    </p>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>組織</th>
                        <th className="text-right">リーチ</th>
                        <th className="text-right">収益(¥)</th>
                        <th className="text-right">投稿数</th>
                        <th>状態</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orgs.map((o) => (
                        <tr key={o.org_name}>
                          <td className="font-medium">{o.org_name}</td>
                          <td className="text-right">{fmt(o.reach)}</td>
                          <td className="text-right">{fmt(o.revenue)}</td>
                          <td className="text-right">{fmt(o.posts)}</td>
                          <td>
                            {o.reach_but_no_revenue ? (
                              <span className="badge badge-yellow">収益化の余地</span>
                            ) : o.revenue > 0 ? (
                              <span className="badge badge-green">収益化済み</span>
                            ) : (
                              <span className="badge badge-neutral">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </>
  )
}
