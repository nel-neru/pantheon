import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, Layers, Sliders } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import type {
  UiApiCheck,
  UiPageStatus,
  UiStatusReport,
  UiStatusResponse,
  UiStatusUnavailable,
} from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { formatDateTime, formatNumber } from '@/lib/utils'

// 自動更新の間隔（ミリ秒）。
const POLL_INTERVAL_MS = 30_000

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 不正値（null/undefined/NaN）を 0 に丸める防御 coerce。 */
function num(x: unknown): number {
  const n = Number(x)
  return Number.isFinite(n) ? n : 0
}

/** レスポンスが生成済みレポートか（available !== false）を判別する型ガード。 */
function isReport(res: UiStatusResponse): res is UiStatusReport {
  return (res as UiStatusUnavailable).available !== false
}

/** ページ status → バッジ配色。 */
function pageStatusBadge(status: string): string {
  switch (status) {
    case 'ok':
      return 'badge-green'
    case 'degraded':
      return 'badge-yellow'
    case 'error':
      return 'badge-red'
    default:
      return 'badge-neutral'
  }
}

/** ページ status → 日本語ラベル。 */
function pageStatusLabel(status: string): string {
  switch (status) {
    case 'ok':
      return '正常'
    case 'degraded':
      return '一部劣化'
    case 'error':
      return 'エラー'
    default:
      return status
  }
}

/** 生成時刻からの相対鮮度（「たった今」「3分前」など）。不正値は formatDateTime にフォールバック。 */
function formatFreshness(generatedAt: string | null | undefined): string {
  if (!generatedAt) return '—'
  const generated = new Date(generatedAt)
  const ts = generated.getTime()
  if (Number.isNaN(ts)) return formatDateTime(generatedAt)
  const diffSec = Math.floor((Date.now() - ts) / 1000)
  if (diffSec < 0) return 'たった今'
  if (diffSec < 60) return 'たった今'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分前`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}時間前`
  return `${Math.floor(diffSec / 86400)}日前`
}

// ─── Sub-component: single API check row ──────────────────────────────────────

function ApiCheckRow({ check }: { check: UiApiCheck }) {
  return (
    <tr>
      <td>
        <span className={`badge ${check.ok ? 'badge-green' : 'badge-red'}`}>
          {check.ok ? 'OK' : 'NG'}
        </span>
      </td>
      <td className="font-mono text-xs">{check.method}</td>
      <td className="font-mono text-xs break-all" title={check.path}>
        {check.path}
      </td>
      <td className="text-right">{formatNumber(num(check.status_code))}</td>
      <td className="text-right">{formatNumber(num(check.latency_ms))} ms</td>
      <td className="text-xs text-muted break-all">{check.error ?? '—'}</td>
    </tr>
  )
}

// ─── Sub-component: per-page card ─────────────────────────────────────────────

function PageStatusCard({ page }: { page: UiPageStatus }) {
  const apis = page.apis ?? []
  const controls = page.controls ?? []
  return (
    <div className="card">
      <div className="card-body flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex flex-col">
            <div className="flex items-center gap-2 font-semibold">
              {page.label || page.route}
              <span className={`badge ${pageStatusBadge(page.status)}`}>
                {pageStatusLabel(page.status)}
              </span>
              {page.static ? <span className="badge badge-neutral">静的</span> : null}
            </div>
            <div className="text-xs text-muted font-mono">{page.route}</div>
          </div>
          <span className="badge badge-neutral">{page.group || '—'}</span>
        </div>

        {apis.length === 0 ? (
          <div className="text-sm text-muted">
            {page.static
              ? 'このページはバックエンド API を直接呼び出しません（静的）。'
              : 'チェック対象の API がありません。'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>結果</th>
                  <th>メソッド</th>
                  <th>パス</th>
                  <th className="text-right">ステータス</th>
                  <th className="text-right">レイテンシ</th>
                  <th>エラー</th>
                </tr>
              </thead>
              <tbody>
                {apis.map((check, index) => (
                  <ApiCheckRow key={`${check.method}-${check.path}-${index}`} check={check} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {controls.length > 0 ? (
          <div className="flex flex-col gap-1">
            <div className="metric-label flex items-center gap-1">
              <Sliders size={13} />
              コントロール
            </div>
            <div className="flex flex-wrap gap-2">
              {controls.map((control, index) => (
                <span key={`${control}-${index}`} className="badge badge-neutral">
                  {control}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

// ─── Page component ───────────────────────────────────────────────────────────

export function UiStatusPage() {
  const [report, setReport] = useState<UiStatusReport | null>(null)
  // available:false（未生成）かどうか。null = まだ判定前。
  const [unavailableMessage, setUnavailableMessage] = useState<string | null>(null)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)

  // 判別ユニオンのレスポンスを state へ反映する共通処理。
  const applyResponse = useCallback((res: UiStatusResponse) => {
    if (isReport(res)) {
      setReport(res)
      setAvailable(true)
      setUnavailableMessage(null)
    } else {
      setReport(null)
      setAvailable(false)
      setUnavailableMessage(res.message ?? null)
    }
  }, [])

  // GET /api/ui/status（初回・ポーリング・再試行で使用）。
  const load = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) setLoading(true)
      try {
        const res = await api<UiStatusResponse>('GET', '/api/ui/status')
        applyResponse(res)
        setError(null)
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'UI 状態の読み込みに失敗しました。'
        if (!opts.silent) {
          setError(message)
          setReport(null)
          setAvailable(null)
        }
      } finally {
        if (!opts.silent) setLoading(false)
      }
    },
    [applyResponse]
  )

  useEffect(() => {
    void load()
  }, [load])

  // 自動更新トグル: ON で 30 秒ごとに silent ポーリング。アンマウント/OFF で解除。
  // applyResponse / load を deps から外すため最新の load を ref で保持する。
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => {
    if (!autoRefresh) return undefined
    const interval = window.setInterval(() => {
      void loadRef.current({ silent: true })
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [autoRefresh])

  // POST /api/ui/status/refresh で今すぐ再チェック。
  const handleRecheck = useCallback(async () => {
    setRefreshing(true)
    try {
      const res = await api<UiStatusReport>('POST', '/api/ui/status/refresh')
      applyResponse(res)
      setError(null)
      toast.success('UI 状態を再チェックしました。')
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'UI 状態の再チェックに失敗しました。'
      toast.error(message)
    } finally {
      setRefreshing(false)
    }
  }, [applyResponse])

  const overall = report?.overall
  const pages = report?.pages ?? []

  const actions = (
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={autoRefresh}
          onChange={(event) => setAutoRefresh(event.target.checked)}
          aria-label="自動更新（30秒ごと）"
        />
        自動更新
      </label>
      <RefreshButton onClick={() => void handleRecheck()} busy={refreshing} label="再チェック" />
    </div>
  )

  return (
    <>
      <PageHeader
        title="UI状態監視"
        subtitle="各ページの到達性・API ヘルス・コントロールを実チェックで監視します"
        actions={actions}
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="UI 状態を読み込み中…"
          errorTitle="UI 状態の読み込みに失敗しました"
        >
          {available === false ? (
            // 未生成 — facade を出さず正直な空状態を提示し、再チェックで生成させる。
            <div className="card">
              <div className="card-body">
                <div className="empty-state">
                  <Activity className="empty-state-icon" size={28} />
                  <h3>未生成</h3>
                  <p>{unavailableMessage ?? '「再チェック」で UI 状態を生成します。'}</p>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void handleRecheck()}
                    disabled={refreshing}
                  >
                    再チェック
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <>
              {/* 全体サマリ */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="card">
                  <div className="card-body">
                    <div className="metric-label flex items-center gap-1">
                      <Layers size={13} />
                      ページ数
                    </div>
                    <div className="metric-value">{formatNumber(num(overall?.pages))}</div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-body">
                    <div className="metric-label flex items-center gap-1">
                      <CheckCircle size={13} />
                      正常
                    </div>
                    <div className="metric-value">{formatNumber(num(overall?.ok))}</div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-body">
                    <div className="metric-label flex items-center gap-1">
                      <Activity size={13} />
                      一部劣化
                    </div>
                    <div className="metric-value">{formatNumber(num(overall?.degraded))}</div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-body">
                    <div className="metric-label flex items-center gap-1">
                      <AlertTriangle size={13} />
                      エラー
                    </div>
                    <div className="metric-value">{formatNumber(num(overall?.error))}</div>
                  </div>
                </div>
              </div>

              {/* 鮮度 + API 集計 */}
              <div className="card">
                <div className="card-body flex items-center gap-4 flex-wrap text-sm text-muted">
                  <span className="flex items-center gap-1">
                    <Clock size={14} />
                    最終チェック: {formatFreshness(report?.generated_at)}
                    {report?.generated_at ? `（${formatDateTime(report.generated_at)}）` : ''}
                  </span>
                  <span>
                    API: {formatNumber(num(overall?.ok_apis))} / {formatNumber(num(overall?.total_apis))} 正常
                  </span>
                </div>
              </div>

              {/* ページ毎カード */}
              {pages.length === 0 ? (
                <div className="card">
                  <div className="card-body">
                    <div className="empty-state">
                      <Activity className="empty-state-icon" size={28} />
                      <h3>ページがありません</h3>
                      <p>「再チェック」で UI 状態を再生成します。</p>
                    </div>
                  </div>
                </div>
              ) : (
                pages.map((page) => <PageStatusCard key={page.route} page={page} />)
              )}
            </>
          )}
        </AsyncBoundary>
      </div>
    </>
  )
}
