import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CalendarDays,
  Coins,
  Download,
  Eye,
  Lightbulb,
  Play,
  Plus,
  Send,
  Square,
  Target,
  TrendingUp,
  Upload,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { formatNumber, formatYen } from '@/lib/utils'

// ─── Types ───────────────────────────────────────────────────────────────────

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

// 月収益目標に対するギャップ（GET /api/hq/portfolio/plan の gap・起票しないプレビュー）
type PlanGap = {
  target: number
  current: number
  forecast: number
  present_gap: number
  forecast_gap: number
  under_target: boolean
}

type PlanPreview = {
  gap: PlanGap
  plan: PortfolioProposal[]
}

const REVENUE_METRICS = ['revenue', 'sales', 'conversions'] as const
type RevenueMetric = (typeof REVENUE_METRICS)[number]

// ─── Label maps ──────────────────────────────────────────────────────────────

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

const METRIC_LABEL: Record<RevenueMetric, string> = {
  revenue: '売上',
  sales: '受注',
  conversions: 'CV',
}

/** メトリクス種別に応じた単位ヒント */
const METRIC_UNIT_HINT: Record<RevenueMetric, string> = {
  revenue: '金額（円）',
  sales: '受注件数',
  conversions: 'CV件数',
}

/** ポートフォリオ提案 kind の和訳ラベル */
const KIND_LABEL: Record<string, string> = {
  portfolio_allocation: '配分',
  monetization: '収益化',
  traffic: '送客',
  new_business: '新規事業',
  investment: '投資',
}

/** ポートフォリオ提案 kind のバッジ配色 */
const KIND_BADGE: Record<string, string> = {
  portfolio_allocation: 'badge-blue',
  monetization: 'badge-green',
  traffic: 'badge-neutral',
  new_business: 'badge-yellow',
  investment: 'badge-red',
}

function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind
}

function kindBadge(kind: string): string {
  return KIND_BADGE[kind] ?? 'badge-neutral'
}

// ─── Page component ───────────────────────────────────────────────────────────

export function RevenuePage() {
  const navigate = useNavigate()
  const formRef = useRef<HTMLDivElement>(null)

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
  // 起票しないプレビュー（GET /api/hq/portfolio/plan）。null = 未取得（プレビュー前）。
  const [planPreview, setPlanPreview] = useState<PlanPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)

  // P14 収益デーモン制御
  const [daemonRunning, setDaemonRunning] = useState<boolean | null>(null)
  const [daemonTarget, setDaemonTarget] = useState('')
  const [daemonBusy, setDaemonBusy] = useState(false)

  // P22 CSV インポート
  const [importText, setImportText] = useState('')
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      type DaemonsStatusShape = { daemons: Record<string, { running?: unknown }> }
      const [result, rep, ai, pf, daemonStatus] = await Promise.all([
        api<RevenueMetrics>('GET', '/api/metrics/revenue'),
        api<RevenueReport>('GET', '/api/metrics/revenue/report'),
        api<RevenueIntelligence>('GET', '/api/metrics/revenue/intelligence'),
        api<{ proposals: PortfolioProposal[] }>('GET', '/api/hq/portfolio'),
        api<DaemonsStatusShape>('GET', '/api/daemons/status').catch(() => null),
      ])
      setData(result ?? null)
      setReport(rep ?? null)
      setIntel(ai ?? null)
      setPortfolio(Array.isArray(pf?.proposals) ? pf.proposals : [])
      // daemon 状態を coerce（free-form payload）
      const rev = daemonStatus?.daemons?.['revenue']
      setDaemonRunning(rev ? Boolean(rev.running) : false)
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
      toast.error('数値を入力してください。')
      return
    }
    // 既存org候補に存在しない org 名は警告（typo防止）
    const orgs = data?.orgs ?? []
    const known = orgs.map((o) => o.org_name)
    if (known.length > 0 && !known.includes(org)) {
      toast('入力した組織名は既存組織と一致しません。新規組織として記録します。', { icon: '⚠️' })
    }
    setSubmitting(true)
    try {
      await api('POST', '/api/outcomes', {
        org_name: org,
        metric: formMetric,
        value,
        note: formNote.trim(),
      })
      toast.success(`${org} に ${METRIC_LABEL[formMetric]} ${formatNumber(value)} を記録しました。`)
      setFormValue('')
      setFormNote('')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '記録に失敗しました。')
    } finally {
      setSubmitting(false)
    }
  }, [formOrg, formMetric, formValue, formNote, data, load])

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
        toast.success(
          `月${formatYen(target)}目標のプランを ${res.proposals} 件、承認キューに起票しました。`
        )
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'プラン生成に失敗しました。')
    } finally {
      setPlanning(false)
    }
  }, [targetInput])

  // 起票せずに目標とのギャップ＋打ち手をプレビューする（GET）。payload は free-form なので防御的に coerce。
  const previewPlan = useCallback(async () => {
    const target = Number(targetInput)
    if (!targetInput.trim() || Number.isNaN(target) || target <= 0) {
      toast.error('月次目標額（正の数値）を入力してください。')
      return
    }
    setPreviewing(true)
    try {
      const res = await api<{ gap?: Partial<PlanGap>; plan?: PortfolioProposal[] }>(
        'GET',
        `/api/hq/portfolio/plan?target=${encodeURIComponent(String(target))}`
      )
      const num = (x: unknown): number => (Number.isFinite(Number(x)) ? Number(x) : 0)
      const g = res.gap ?? {}
      const plan = (Array.isArray(res.plan) ? res.plan : []).map((e) => ({
        kind: String(e?.kind ?? ''),
        title: String(e?.title ?? ''),
        reason: String(e?.reason ?? ''),
        priority: num(e?.priority),
      }))
      setPlanPreview({
        gap: {
          target: num(g.target),
          current: num(g.current),
          forecast: num(g.forecast),
          present_gap: num(g.present_gap),
          forecast_gap: num(g.forecast_gap),
          under_target: Boolean(g.under_target),
        },
        plan,
      })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'プレビューに失敗しました。')
    } finally {
      setPreviewing(false)
    }
  }, [targetInput])

  // P14 — 収益デーモン起動（月次目標を送信）
  const startDaemon = useCallback(async () => {
    const target = Number(daemonTarget)
    const hasTarget = daemonTarget.trim() !== '' && Number.isFinite(target) && target > 0
    setDaemonBusy(true)
    try {
      await api('POST', '/api/daemons/revenue/start', hasTarget ? { target } : {})
      setDaemonRunning(true)
      toast.success(
        hasTarget
          ? `収益デーモンを起動しました（月次目標: ${formatYen(target)}）。`
          : '収益デーモンをアイドル安全モードで起動しました。'
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '収益デーモンの起動に失敗しました。')
    } finally {
      setDaemonBusy(false)
    }
  }, [daemonTarget])

  // P14 — 収益デーモン停止
  const stopDaemon = useCallback(async () => {
    setDaemonBusy(true)
    try {
      await api('POST', '/api/daemons/revenue/stop')
      setDaemonRunning(false)
      toast.success('収益デーモンを停止しました。')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '収益デーモンの停止に失敗しました。')
    } finally {
      setDaemonBusy(false)
    }
  }, [])

  // P22 — CSV/JSON インポート（テキストエリアの内容を /api/outcomes/import に送信）
  const runImport = useCallback(async () => {
    const text = importText.trim()
    if (!text) {
      toast.error('インポートするデータを入力してください。')
      return
    }
    setImporting(true)
    try {
      // JSON 配列もしくは CSV（1行目はヘッダ）を受け付ける
      let rows: Record<string, unknown>[]
      const firstChar = text[0]
      if (firstChar === '[' || firstChar === '{') {
        // JSON パス
        const parsed: unknown = JSON.parse(text)
        rows = Array.isArray(parsed) ? (parsed as Record<string, unknown>[]) : [parsed as Record<string, unknown>]
      } else {
        // CSV パス: 1行目ヘッダ、以降はデータ行
        const lines = text.split(/\r?\n/).filter((l) => l.trim())
        if (lines.length < 2) throw new Error('CSV にはヘッダ行とデータ行が必要です。')
        const headers = lines[0].split(',').map((h) => h.trim())
        rows = lines.slice(1).map((line) => {
          const values = line.split(',')
          const record: Record<string, unknown> = {}
          headers.forEach((h, idx) => {
            record[h] = values[idx]?.trim() ?? ''
          })
          return record
        })
      }
      const res = await api<{ imported: number; skipped: number; orgs: string[] }>(
        'POST',
        '/api/outcomes/import',
        { rows }
      )
      toast.success(`${res.imported} 件をインポートしました（スキップ: ${res.skipped} 件）。`)
      setImportText('')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'インポートに失敗しました。')
    } finally {
      setImporting(false)
    }
  }, [importText, load])

  const orgs = data?.orgs ?? []
  const alerts = orgs.filter((o) => o.reach_but_no_revenue)

  // 月次データを month キーで明示ソート（API キー順依存を除去）
  const months = report
    ? Object.entries(report.by_month).sort(([a], [b]) => a.localeCompare(b))
    : []

  // 前月比計算
  function calcDelta(i: number): number | null {
    if (i === 0) return null
    const prev = months[i - 1][1]
    if (prev === 0) return null
    return Math.round(((months[i][1] - prev) / prev) * 1000) / 10
  }

  // P22 — CSV エクスポート（月次テーブルをクライアントサイド Blob で出力）
  // months / calcDelta の後に定義することで TDZ エラーを回避。
  const exportCsv = () => {
    if (months.length === 0) {
      toast.error('エクスポートするデータがありません。')
      return
    }
    const csvRows = [
      ['月', '収益(¥)', '前月比(%)'],
      ...months.map(([month, total], i) => {
        const delta = calcDelta(i)
        const safeTotal = Math.round(Number.isFinite(total) ? total : 0)
        return [month, String(safeTotal), delta === null ? '' : String(delta)]
      }),
    ]
    const csv = csvRows.map((r) => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'revenue_monthly.csv'
    a.click()
    URL.revokeObjectURL(url)
    toast.success('CSV をエクスポートしました。')
  }

  // priority 降順ソートされたポートフォリオ提案
  const sortedPortfolio = [...portfolio].sort((a, b) => b.priority - a.priority)

  // 手動フォームにスクロール
  const scrollToForm = () => {
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <PageHeader
        title="収益ダッシュボード"
        actions={
          <RefreshButton onClick={() => void load()} busy={loading} />
        }
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="収益メトリクスを読み込み中…"
          errorTitle="収益メトリクスの読み込みに失敗しました"
        >
          {/* KPI カード（3種） */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <Coins size={14} />
                  累計収益
                </div>
                <div className="metric-value">{formatYen(data?.total_revenue ?? 0)}</div>
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <TrendingUp size={14} />
                  累計リーチ
                </div>
                <div className="metric-value">{formatNumber(data?.total_reach ?? 0)}</div>
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="metric-label flex items-center gap-1">
                  <Send size={14} />
                  収益密度（¥/投稿）
                </div>
                <div className="metric-value" id="metric-total-posts">
                  {(() => {
                    const totalPosts = orgs.reduce((sum, o) => sum + o.posts, 0)
                    const totalRev = data?.total_revenue ?? 0
                    return totalPosts > 0 ? formatYen(Math.round(totalRev / totalPosts)) : '—'
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* 手動記録フォーム */}
          <div className="card" ref={formRef}>
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Plus size={16} />
                <div className="font-semibold">収益・成果を手動で記録</div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">組織</span>
                  <input
                    id="form-org-input"
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
                    id="form-metric-select"
                    className="select"
                    value={formMetric}
                    onChange={(e) => setFormMetric(e.target.value as RevenueMetric)}
                  >
                    {REVENUE_METRICS.map((m) => (
                      <option key={m} value={m}>
                        {METRIC_LABEL[m]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">{METRIC_UNIT_HINT[formMetric]}</span>
                  <input
                    className="input"
                    type="number"
                    inputMode="numeric"
                    placeholder="0"
                    value={formValue}
                    onChange={(e) => setFormValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void submitOutcome()
                    }}
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

          {/* 収益トレンド（insufficient のときも淡色で表示） */}
          {intel ? (
            <div id="trend-card" className="card">
              <div className="card-body flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <TrendingUp size={16} />
                  <div className="font-semibold">収益トレンド（全組織）</div>
                  <span className={`badge ${TREND_BADGE[intel.trend]}`}>
                    {TREND_LABEL[intel.trend]}
                  </span>
                </div>
                {intel.trend === 'insufficient' ? (
                  <div className="text-sm text-muted">
                    データ蓄積中です。2ヶ月以上の記録が揃うと予測が始まります。
                  </div>
                ) : (
                  <div className="flex items-center gap-4 text-sm">
                    {intel.latest_change_pct !== null ? (
                      <span className="text-muted">
                        前月比{' '}
                        <span className="font-medium">
                          {intel.latest_change_pct > 0 ? '+' : ''}
                          {intel.latest_change_pct}%
                        </span>
                      </span>
                    ) : null}
                    <span className="text-muted" id="trend-forecast">
                      翌月予測{' '}
                      <span className="font-medium">{formatYen(intel.forecast_next)}</span>
                      <span className="text-muted text-xs ml-1" title="過去月次データの線形近似による点予測。実績との乖離が生じる場合があります。">
                        （概算）
                      </span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {/* ポートフォリオ提案（HQ）— priority 降順・行動ボタン付き */}
          {sortedPortfolio.length > 0 ? (
            <div id="portfolio-card" className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Lightbulb size={16} />
                  <div className="font-semibold">ポートフォリオ提案（HQ）</div>
                </div>
                <p className="text-muted text-sm">
                  各組織の収益/リーチから「投資・収益化・送客」の打ち手を提案します。提案は自動実行されません。
                </p>
                {sortedPortfolio.map((p, i) => (
                  <div
                    id="portfolio-proposal-row"
                    key={`${p.kind}-${p.priority}-${i}`}
                    className="flex items-start justify-between gap-3 flex-wrap border-t border-base pt-3 first:border-t-0 first:pt-0"
                  >
                    <div className="flex items-start gap-2 min-w-0 flex-1">
                      <span className={`badge ${kindBadge(p.kind)} shrink-0`}>
                        {kindLabel(p.kind)}
                      </span>
                      <div className="min-w-0">
                        <div className="font-medium truncate">{p.title}</div>
                        <div className="text-sm text-muted">{p.reason}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => navigate('/handoffs')}
                      >
                        <Eye size={14} />
                        承認インボックスで開く
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* 自律経営プラン */}
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
                  id="target-input"
                  className="input w-48"
                  type="number"
                  min={0}
                  placeholder="月次目標額（円）"
                  value={targetInput}
                  onChange={(e) => setTargetInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void runTargetPlan()
                  }}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={previewing}
                  onClick={() => void previewPlan()}
                  title="起票せずに、目標とのギャップと打ち手だけを確認します"
                >
                  <Eye size={14} />
                  {previewing ? 'プレビュー中…' : 'プランをプレビュー'}
                </button>
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
              {planPreview !== null && (
                <div
                  id="plan-preview"
                  className="rounded-xl border border-white/10 p-3 flex flex-col gap-3"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Eye size={14} />
                    プランプレビュー（未起票）
                  </div>
                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                    <span>
                      <span className="text-muted">現状（月次）: </span>
                      <span className="font-medium">{formatYen(planPreview.gap.current)}</span>
                    </span>
                    <span>
                      <span className="text-muted">目標: </span>
                      <span className="font-medium">{formatYen(planPreview.gap.target)}</span>
                    </span>
                    <span>
                      <span className="text-muted">ギャップ: </span>
                      <span
                        className={`font-medium ${
                          planPreview.gap.under_target ? 'text-yellow' : 'text-green-600'
                        }`}
                      >
                        {formatYen(planPreview.gap.present_gap)}
                      </span>
                    </span>
                    <span>
                      <span className="text-muted">翌月予測: </span>
                      <span className="font-medium">{formatYen(planPreview.gap.forecast)}</span>
                    </span>
                  </div>
                  {planPreview.plan.length === 0 ? (
                    <div className="text-muted text-sm">
                      目標達成済み、または提案できる打ち手がありません。
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {planPreview.plan.map((p, i) => (
                        <div
                          key={`${p.kind}-${i}`}
                          className="flex items-start gap-2 border-t border-base pt-2 first:border-t-0 first:pt-0"
                        >
                          <span className={`badge ${kindBadge(p.kind)} shrink-0`}>
                            {kindLabel(p.kind)}
                          </span>
                          <div className="min-w-0">
                            <div className="font-medium">{p.title}</div>
                            <div className="text-sm text-muted">{p.reason}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* P14: 自律経営（収益デーモン）コントロール */}
          <div id="daemon-control-card" className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Zap size={16} />
                <div className="font-semibold">自律経営（収益デーモン）</div>
                {daemonRunning === true ? (
                  <span className="badge badge-green">稼働中</span>
                ) : daemonRunning === false ? (
                  <span className="badge badge-neutral">停止中</span>
                ) : null}
              </div>
              <p className="text-muted text-sm">
                月次目標を設定してデーモンを起動すると、自律的にポートフォリオ提案・HQ介入を繰り返す
                継続ループが動きます（目標省略 = アイドル安全モード）。停止はいつでもできます。
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  id="daemon-target-input"
                  className="input w-48"
                  type="number"
                  min={0}
                  placeholder="月次目標額（円）任意"
                  value={daemonTarget}
                  onChange={(e) => setDaemonTarget(e.target.value)}
                />
                <button
                  id="daemon-start-button"
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={daemonBusy || daemonRunning === true}
                  onClick={() => void startDaemon()}
                >
                  <Play size={14} />
                  {daemonBusy ? '処理中…' : '起動'}
                </button>
                <button
                  id="daemon-stop-button"
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={daemonBusy || daemonRunning === false}
                  onClick={() => void stopDaemon()}
                >
                  <Square size={14} />
                  停止
                </button>
              </div>
            </div>
          </div>

          {/* 月次収益レポート（month キーソート＋前月比列） */}
          <div id="monthly-report-card" className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <CalendarDays size={16} />
                  <div className="font-semibold">月次収益レポート（全組織）</div>
                </div>
                <button
                  id="export-csv-button"
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={months.length === 0}
                  onClick={exportCsv}
                >
                  <Download size={14} />
                  エクスポート (CSV)
                </button>
              </div>
              {months.length === 0 ? (
                <div className="text-sm text-muted">月次データが蓄積されると表示されます。</div>
              ) : (
                <table id="monthly-report-table" className="data-table">
                  <thead>
                    <tr>
                      <th>月</th>
                      <th className="text-right">収益(¥)</th>
                      <th className="text-right">前月比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {months.map(([month, total], i) => {
                      const delta = calcDelta(i)
                      return (
                        <tr key={month}>
                          <td className="font-medium">{month}</td>
                          <td className="text-right">{formatYen(total)}</td>
                          <td className="text-right">
                            {delta === null ? (
                              <span className="text-muted">—</span>
                            ) : (
                              <span className={delta >= 0 ? 'text-green-600' : 'text-red-500'}>
                                {delta > 0 ? '+' : ''}
                                {delta}%
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* P22: CSV/JSON インポート */}
          <div id="import-card" className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Upload size={16} />
                <div className="font-semibold">成果データを一括インポート</div>
              </div>
              <p className="text-muted text-sm">
                CSV（1行目: ヘッダ）または JSON 配列を貼り付けて一括取り込みします。
                CSV ヘッダ例: <code>org_name,metric,value,note</code>
              </p>
              <textarea
                id="import-textarea"
                className="input font-mono text-xs"
                rows={4}
                placeholder={'org_name,metric,value,note\nMy Co,revenue,5000,6月分'}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
              <div className="flex justify-end">
                <button
                  id="import-button"
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={importing || !importText.trim()}
                  onClick={() => void runImport()}
                >
                  <Upload size={14} />
                  {importing ? 'インポート中…' : 'インポート'}
                </button>
              </div>
            </div>
          </div>

          {/* 収益化余地アラート（org ごとに /handoffs?org=xxx へ遷移） */}
          {alerts.length > 0 ? (
            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={16} className="text-yellow" />
                  <div className="font-semibold">リーチはあるが収益0の組織（収益化の余地）</div>
                </div>
                {alerts.map((o) => (
                  <div
                    key={o.org_name}
                    className="flex items-center justify-between gap-2 flex-wrap"
                  >
                    <div className="text-sm">
                      <span className="font-medium">{o.org_name}</span>
                      <span className="text-muted">
                        {' '}
                        ・ リーチ {formatNumber(o.reach)} / 収益 ¥0
                      </span>
                    </div>
                    <button
                      id="alert-handoff-button"
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() =>
                        navigate(`/handoffs?org=${encodeURIComponent(o.org_name)}`)
                      }
                    >
                      <Eye size={14} />
                      {o.org_name} の引き渡しを確認
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* 組織別テーブル / 空状態 */}
          <div className="card">
            <div className="card-body">
              {orgs.length === 0 ? (
                <div className="empty-state" id="orgs-empty-state">
                  <Coins className="empty-state-icon" size={28} />
                  <h3>成果データがありません</h3>
                  <p>上の手動記録フォームから収益・成果を記録できます。</p>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={scrollToForm}
                  >
                    <Plus size={14} />
                    手動記録フォームへ
                  </button>
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
                        <td className="text-right">{formatNumber(o.reach)}</td>
                        <td className="text-right">{formatYen(o.revenue)}</td>
                        <td className="text-right">{formatNumber(o.posts)}</td>
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
        </AsyncBoundary>
      </div>
    </>
  )
}
