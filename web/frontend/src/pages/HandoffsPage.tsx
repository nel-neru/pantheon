import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ArrowRightLeft, CheckCircle, FileText, XCircle } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

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

function statusLabel(status: string) {
  if (status === 'pending') return '承認待ち'
  if (status === 'approved') return '承認済み'
  if (status === 'consumed') return '消費済み'
  if (status === 'rejected') return '却下'
  return status
}

function statusBadge(status: string) {
  if (status === 'approved') return 'badge-green'
  if (status === 'rejected') return 'badge-red'
  if (status === 'consumed') return 'badge-blue'
  return 'badge-yellow'
}

export function HandoffsPage() {
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>('pending')
  const [actionId, setActionId] = useState<string | null>(null)

  const loadHandoffs = useCallback(async (status: string) => {
    setLoading(true)
    try {
      const query = status === 'all' ? '' : `?status=${encodeURIComponent(status)}`
      const data = await api<Handoff[]>('GET', `/api/handoffs${query}`)
      setHandoffs(data)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '引き渡しの読み込みに失敗しました。'
      setHandoffs([])
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHandoffs(statusFilter)
  }, [loadHandoffs, statusFilter])

  const handleApprove = async (handoff: Handoff) => {
    setActionId(handoff.handoff_id)
    try {
      const result = await api<Handoff & { materialized: Materialized }>(
        'POST',
        `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/approve`,
      )
      if (result.materialized) {
        toast.success(
          `承認しました。受け手「${result.materialized.org_name}」にブリーフ提案を自動生成: ${result.materialized.title}`,
        )
      } else {
        toast.success('承認しました。')
      }
      await loadHandoffs(statusFilter)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '承認に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  const handleDraft = async (handoff: Handoff) => {
    setActionId(handoff.handoff_id)
    try {
      const result = await api<{ org_name: string; title: string }>(
        'POST',
        `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/draft`,
      )
      toast.success(`本文ドラフトを生成しました（${result.org_name}「${result.title}」）。`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '本文生成に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  const handleReject = async (handoff: Handoff) => {
    setActionId(handoff.handoff_id)
    try {
      await api<Handoff>('POST', `/api/handoffs/${encodeURIComponent(handoff.handoff_id)}/reject`)
      toast.success('却下しました。')
      await loadHandoffs(statusFilter)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '却下に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">引き渡し（集客→販売→収益化）</div>
        <div className="page-actions">
          <select
            className="select"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as (typeof STATUS_FILTERS)[number])}
          >
            {STATUS_FILTERS.map((status) => (
              <option key={status} value={status}>
                {status === 'all' ? 'すべて' : statusLabel(status)}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
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
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadHandoffs(statusFilter)}>
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
                <p>SNS運用→note販売→アフィリの引き渡しを作成すると、ここに承認待ちが並びます。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error
          ? handoffs.map((handoff) => (
              <div key={handoff.handoff_id} className="proposal-card">
                <div className="proposal-header">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <div className="font-semibold truncate">{handoff.title}</div>
                      <span className="badge badge-neutral">{handoff.kind}</span>
                      <span className={`badge ${statusBadge(handoff.status)}`}>{statusLabel(handoff.status)}</span>
                    </div>
                    <div className="text-sm text-fg2 flex items-center gap-2">
                      <span className="font-medium">{handoff.source_org}</span>
                      <ArrowRightLeft size={14} />
                      <span className="font-medium">{handoff.target_org}</span>
                    </div>
                  </div>
                </div>
                <div className="proposal-body flex flex-col gap-3">
                  {Object.keys(handoff.payload ?? {}).length > 0 ? (
                    <div>
                      <div className="metric-label">ペイロード</div>
                      <pre className="progress-log mt-2" style={{ whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(handoff.payload, null, 2)}
                      </pre>
                    </div>
                  ) : null}
                  <div className="text-sm text-muted">
                    ポリシー: {handoff.policy_decision || '—'}
                    {handoff.materialized_ref ? ` / 生成提案: ${handoff.materialized_ref.slice(0, 8)}` : ''}
                  </div>
                </div>
                <div className="proposal-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm text-green"
                    onClick={() => void handleApprove(handoff)}
                    disabled={actionId === handoff.handoff_id || handoff.status !== 'pending'}
                  >
                    <CheckCircle size={14} />
                    {actionId === handoff.handoff_id ? '更新中' : '承認'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => void handleReject(handoff)}
                    disabled={actionId === handoff.handoff_id || handoff.status !== 'pending'}
                  >
                    <XCircle size={14} />
                    {actionId === handoff.handoff_id ? '更新中' : '却下'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void handleDraft(handoff)}
                    disabled={
                      actionId === handoff.handoff_id ||
                      handoff.status === 'rejected' ||
                      handoff.status === 'consumed'
                    }
                    title="受け手 org に本文ドラフト提案を生成します"
                  >
                    <FileText size={14} />
                    {actionId === handoff.handoff_id ? '生成中' : '本文生成'}
                  </button>
                </div>
              </div>
            ))
          : null}
      </div>
    </>
  )
}
