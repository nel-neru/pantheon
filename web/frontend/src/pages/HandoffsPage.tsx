import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle,
  ChevronDown,
  FileText,
  RefreshCw,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { statusLabel, statusBadge } from '@/lib/labels'

type Handoff = {
  handoff_id: string
  source_org: string
  target_org: string
  kind: string
  title: string
  payload: Record<string, unknown>
  status: string
  priority: string
  note: string
  policy_decision: string
  policy_reason: string
  consumed_ref: string
  materialized_ref: string
}

type Materialized = {
  proposal_id: string
  org_name: string
  title: string
  file_path: string
} | null

const STATUS_FILTERS = ['pending', 'approved', 'consumed', 'rejected', 'all'] as const
type StatusFilter = (typeof STATUS_FILTERS)[number]

// handoff 固有のラベル補完（lib/labels にない consumed を上書き）。
// consumed の共通ラベル追加は shared_needs 経由で lib/labels に依頼済み。
function handoffStatusLabel(status: string): string {
  if (status === 'pending') return '承認待ち'
  if (status === 'consumed') return '消費済み'
  return statusLabel(status)
}

function handoffStatusBadge(status: string): string {
  if (status === 'consumed') return 'badge-blue'
  return statusBadge(status)
}

// kind の日本語ラベル（英語スラッグを運用者向けに和訳）。
function kindLabel(kind: string): string {
  if (kind === 'audience_signal') return '集客シグナル'
  if (kind === 'content_handoff') return 'コンテンツ'
  if (kind === 'revenue_signal') return '収益シグナル'
  if (kind === 'campaign') return 'キャンペーン'
  if (kind === 'draft') return '下書き'
  return kind
}

// フィルタ別の空状態文言。
function emptyTextForFilter(filter: StatusFilter): string {
  if (filter === 'pending') return '承認待ちの引き渡しはありません。SNS運用→note販売→アフィリの処理が進むと、ここに承認待ちが並びます。'
  if (filter === 'approved') return '承認済みの引き渡しはありません。'
  if (filter === 'consumed') return '消費済みの引き渡しはありません。'
  if (filter === 'rejected') return '却下された引き渡しはありません。'
  return '引き渡しはありません。'
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

// ペイロードの主要キーを定義リスト風に整形する。
function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const entries = Object.entries(payload ?? {})
  if (entries.length === 0) return null

  // 1段階のプリミティブ値だけ見せ、残りは Raw に。
  const primitiveEntries = entries.filter(([, v]) => typeof v !== 'object' || v === null)
  const hasComplex = entries.some(([, v]) => typeof v === 'object' && v !== null)

  return (
    <div className="flex flex-col gap-1">
      <div className="metric-label">ペイロード</div>
      {primitiveEntries.length > 0 ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm mt-1">
          {primitiveEntries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted font-medium whitespace-nowrap">{key}</dt>
              <dd className="text-fg truncate">{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {(hasComplex || entries.length > primitiveEntries.length) ? (
        <div className="mt-1">
          <button
            type="button"
            className="btn btn-ghost btn-sm flex items-center gap-1 text-xs"
            onClick={() => setOpen((prev) => !prev)}
          >
            <ChevronDown size={12} className={open ? 'rotate-180' : ''} />
            Raw JSON
          </button>
          {open ? (
            <pre className="progress-log mt-1 whitespace-pre-wrap max-h-48 overflow-y-auto text-xs">
              {JSON.stringify(payload, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function HandoffsPage() {
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [quietLoading, setQuietLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending')
  // action keys: 'approve:<id>' | 'reject:<id>' | 'draft:<id>'
  const [actionId, setActionId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

  const loadHandoffs = useCallback(async (status: string, quiet = false) => {
    if (!quiet) setLoading(true)
    else setQuietLoading(true)
    try {
      const query = status === 'all' ? '' : `?status=${encodeURIComponent(status)}`
      const data = await api<Handoff[]>('GET', `/api/handoffs${query}`)
      setHandoffs(Array.isArray(data) ? data : [])
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '引き渡しの読み込みに失敗しました。'
      if (!quiet) setHandoffs([])
      setError(message)
      // toast は出さない。ローディング失敗（全画面空）はインラインカードのみ通知する。
    } finally {
      setLoading(false)
      setQuietLoading(false)
    }
  }, [])

  // 各フィルタの件数を取得（ヘッダーのバッジ表示用）。
  const loadCounts = useCallback(async () => {
    try {
      const results = await Promise.allSettled(
        (['pending', 'approved', 'consumed', 'rejected'] as const).map((s) =>
          api<Handoff[]>('GET', `/api/handoffs?status=${encodeURIComponent(s)}`),
        ),
      )
      const counts: Record<string, number> = {}
      const statuses = ['pending', 'approved', 'consumed', 'rejected'] as const
      results.forEach((r, i) => {
        if (r.status === 'fulfilled' && Array.isArray(r.value)) {
          counts[statuses[i]] = r.value.length
        }
      })
      setStatusCounts(counts)
    } catch {
      // 件数取得失敗は無視（本体の読み込みには影響しない）。
    }
  }, [])

  useEffect(() => {
    void loadHandoffs(statusFilter)
  }, [loadHandoffs, statusFilter])

  useEffect(() => {
    void loadCounts()
  }, [loadCounts])

  // ConfirmDialog 経由の操作用。失敗時は再 throw してダイアログを開いたまま保持。
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
      await loadHandoffs(statusFilter, true)
      await loadCounts()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const handleApprove = (handoff: Handoff) => {
    setConfirm({
      title: '承認して本文を生成しますか？',
      description: (
        <>
          「{handoff.title}」を承認し、受け手 Org <strong>{handoff.target_org}</strong>{' '}
          の本文ドラフトを claude で自動生成します。
          <br />
          <span className="text-muted text-sm">生成には時間とコストがかかります。承認後は取り消せません。</span>
        </>
      ),
      confirmLabel: '承認＋本文生成',
      run: async () => {
        setActionId(`approve:${handoff.handoff_id}`)
        try {
          const result = await api<Handoff & { materialized: Materialized }>(
            'POST',
            `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/approve`,
            { draft: true },
          )
          const msg =
            result.materialized
              ? `承認し、「${result.materialized.org_name}」に本文ドラフトを生成しました: ${result.materialized.title}`
              : '承認しました。'
          toast.success(msg)
          await loadHandoffs(statusFilter, true)
          await loadCounts()
        } catch (err) {
          toast.error(err instanceof Error ? err.message : '承認に失敗しました。')
          throw err // ConfirmDialog を開いたまま保持する。
        } finally {
          setActionId(null)
        }
      },
    })
  }

  const handleReject = (handoff: Handoff) => {
    setConfirm({
      title: 'この引き渡しを却下しますか？',
      description: (
        <>
          「{handoff.title}」を却下します。
          <br />
          <span className="text-muted text-sm">ステータスは却下に変わり、元に戻すことはできません。</span>
        </>
      ),
      confirmLabel: '却下する',
      run: () =>
        directRun(
          () => api<Handoff>('POST', `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/reject`),
          '却下しました。',
        ),
    })
  }

  const handleDraft = async (handoff: Handoff) => {
    setActionId(`draft:${handoff.handoff_id}`)
    try {
      const result = await api<{ org_name: string; title: string }>(
        'POST',
        `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/draft`,
      )
      toast.success(`本文ドラフトを生成しました（${result.org_name}「${result.title}」）。`)
      // 生成後は materialized_ref が更新されるためリスト再取得。
      await loadHandoffs(statusFilter, true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '本文生成に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  const handleRefresh = () => {
    void loadHandoffs(statusFilter, true)
    void loadCounts()
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">引き渡し（集客→販売→収益化）</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleRefresh}
            disabled={quietLoading}
          >
            <RefreshCw size={14} className={quietLoading ? 'animate-spin' : ''} />
            更新
          </button>
          <div className="flex items-center gap-1">
            <label htmlFor="status-filter" className="text-sm text-muted whitespace-nowrap">
              ステータス
            </label>
            <select
              id="status-filter"
              className="select"
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as StatusFilter)
              }
              aria-label="ステータスフィルタ"
            >
              {STATUS_FILTERS.map((status) => {
                const count = status !== 'all' ? (statusCounts[status] ?? null) : null
                const label =
                  status === 'all'
                    ? 'すべて'
                    : handoffStatusLabel(status)
                return (
                  <option key={status} value={status}>
                    {label}{count !== null ? ` (${count})` : ''}
                  </option>
                )
              })}
            </select>
          </div>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card" role="status" aria-busy="true">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">引き渡しを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>引き渡しの読み込みに失敗しました</h3>
                <p className="text-muted text-sm">データの取得中にエラーが発生しました。</p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void loadHandoffs(statusFilter)}
                >
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && handoffs.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <ArrowRightLeft className="empty-state-icon" size={28} />
                <h3>引き渡しがありません</h3>
                <p>{emptyTextForFilter(statusFilter)}</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error
          ? handoffs.map((handoff) => {
              const approveKey = `approve:${handoff.handoff_id}`
              const rejectKey = `reject:${handoff.handoff_id}`
              const draftKey = `draft:${handoff.handoff_id}`
              const anyBusy =
                actionId === approveKey ||
                actionId === rejectKey ||
                actionId === draftKey
              const isPending = handoff.status === 'pending'
              const canDraft =
                handoff.status !== 'rejected' && handoff.status !== 'consumed'

              return (
                <div key={handoff.handoff_id} className="proposal-card">
                  <div className="proposal-header">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <div className="font-semibold truncate">{handoff.title}</div>
                        {/* kind: icon-style tag で status バッジと視覚差別化 */}
                        <span className="badge badge-neutral text-xs flex items-center gap-1">
                          <ArrowRightLeft size={10} />
                          {kindLabel(handoff.kind)}
                        </span>
                        <span className={`badge ${handoffStatusBadge(handoff.status)}`}>
                          {handoffStatusLabel(handoff.status)}
                        </span>
                      </div>
                      <div className="text-sm text-fg2 flex items-center gap-2 flex-wrap">
                        <span className="font-medium">{handoff.source_org}</span>
                        <ArrowRightLeft size={14} />
                        <span className="font-medium">{handoff.target_org}</span>
                      </div>
                    </div>
                  </div>

                  <div className="proposal-body flex flex-col gap-3">
                    {/* ペイロード: 主要キー定義リスト + Raw 折りたたみ */}
                    <PayloadView payload={handoff.payload ?? {}} />

                    {/* 自動ポリシー判定 */}
                    <div className="flex flex-col gap-1">
                      <div className="metric-label">自動ポリシー判定</div>
                      <div className="text-sm flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-muted">判定:</span>
                          <span>{handoff.policy_decision || '—'}</span>
                        </div>
                        {handoff.policy_reason ? (
                          <div className="flex items-start gap-2">
                            <span className="text-muted whitespace-nowrap">理由:</span>
                            <span className="text-fg2">{handoff.policy_reason}</span>
                          </div>
                        ) : null}
                        {handoff.materialized_ref ? (
                          <div className="flex items-center gap-2">
                            <span className="text-muted whitespace-nowrap">生成済みドラフト:</span>
                            <span className="font-mono text-xs text-fg2 truncate" title={handoff.materialized_ref}>
                              {handoff.materialized_ref}
                            </span>
                          </div>
                        ) : null}
                        {handoff.note ? (
                          <div className="flex items-start gap-2">
                            <span className="text-muted whitespace-nowrap">備考:</span>
                            <span className="text-fg2">{handoff.note}</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="proposal-actions">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm text-green"
                      onClick={() => handleApprove(handoff)}
                      disabled={anyBusy || !isPending}
                      title="承認と同時に受け手 Org の本文ドラフトを claude で自動生成します"
                    >
                      <CheckCircle size={14} />
                      {actionId === approveKey ? '承認中…' : '承認＋本文生成'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => handleReject(handoff)}
                      disabled={anyBusy || !isPending}
                    >
                      <XCircle size={14} />
                      {actionId === rejectKey ? '却下中…' : '却下'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleDraft(handoff)}
                      disabled={anyBusy || !canDraft}
                      title="承認とは別に、受け手 Org の本文ドラフト提案だけを生成/再生成します"
                    >
                      <FileText size={14} />
                      {actionId === draftKey ? '生成中…' : '本文のみ生成'}
                    </button>
                  </div>
                </div>
              )
            })
          : null}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel}
        destructive
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </>
  )
}
