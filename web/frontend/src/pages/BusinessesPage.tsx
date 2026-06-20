import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRightLeft,
  Building2,
  ChevronDown,
  ChevronRight,
  Coins,
  GitMerge,
  Plus,
  Target,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { statusBadge, statusLabel } from '@/lib/labels'
import { formatNumber } from '@/lib/utils'

// ─── Types ───────────────────────────────────────────────────────────────────

type HandoffRoute = {
  from_org: string
  to_org: string
  kind: string
}

type Business = {
  id: string
  name: string
  purpose: string
  member_orgs: string[]
  roles: Record<string, string>
  handoff_routes: HandoffRoute[]
  kpis: string[]
  status: string
  created_at: string
}

type BusinessOutcomes = {
  business: Business
  member_orgs: string[]
  by_metric: Record<string, number>
  event_count: number
  total_revenue: number
  total_reach: number
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  destructive?: boolean
  run: () => Promise<void>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function num(x: unknown): number {
  const n = Number(x)
  return Number.isFinite(n) ? n : 0
}

// ─── Page component ───────────────────────────────────────────────────────────

export function BusinessesPage() {
  const navigate = useNavigate()

  const [businesses, setBusinesses] = useState<Business[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create form
  const [createName, setCreateName] = useState('')
  const [createOrgs, setCreateOrgs] = useState('')
  const [createPurpose, setCreatePurpose] = useState('')
  const [createKpis, setCreateKpis] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)

  // Per-business outcomes panel
  const [outcomesId, setOutcomesId] = useState<string | null>(null)
  const [outcomes, setOutcomes] = useState<BusinessOutcomes | null>(null)
  const [outcomesLoading, setOutcomesLoading] = useState(false)

  // Confirm dialog
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<{ businesses: Business[] }>('GET', '/api/businesses')
      setBusinesses(Array.isArray(res?.businesses) ? res.businesses : [])
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '事業の読み込みに失敗しました。'
      setBusinesses([])
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleCreate = useCallback(async () => {
    const name = createName.trim()
    if (!name) {
      toast.error('事業名を入力してください。')
      return
    }
    setCreating(true)
    try {
      const memberOrgs = createOrgs
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const kpis = createKpis
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      await api<Business>('POST', '/api/businesses', {
        name,
        purpose: createPurpose.trim() || undefined,
        member_orgs: memberOrgs.length > 0 ? memberOrgs : undefined,
        kpis: kpis.length > 0 ? kpis : undefined,
      })
      toast.success(`事業「${name}」を作成しました。`)
      setCreateName('')
      setCreateOrgs('')
      setCreatePurpose('')
      setCreateKpis('')
      setShowCreate(false)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '作成に失敗しました。')
    } finally {
      setCreating(false)
    }
  }, [createName, createOrgs, createPurpose, createKpis, load])

  const handleViewOutcomes = useCallback(async (id: string) => {
    if (outcomesId === id) {
      setOutcomesId(null)
      setOutcomes(null)
      return
    }
    setOutcomesId(id)
    setOutcomesLoading(true)
    try {
      const res = await api<BusinessOutcomes>('GET', `/api/businesses/${encodeURIComponent(id)}/outcomes`)
      setOutcomes(res ?? null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '成果の取得に失敗しました。')
      setOutcomesId(null)
      setOutcomes(null)
    } finally {
      setOutcomesLoading(false)
    }
  }, [outcomesId])

  const handleCompose = useCallback(
    (biz: Business) => {
      setConfirm({
        title: `「${biz.name}」の未完ハンドオフを実体化しますか？`,
        description: '保留中のハンドオフルートを /handoffs に実体化します。',
        confirmLabel: '実体化する',
        destructive: false,
        run: async () => {
          const res = await api<{ created: number; handoff_ids: string[] }>(
            'POST',
            `/api/businesses/${encodeURIComponent(biz.id)}/compose`
          )
          const created = num(res?.created)
          toast.success(
            created > 0
              ? `${created} 件のハンドオフを実体化しました。/handoffs で確認できます。`
              : 'ハンドオフは既に全て実体化されています。'
          )
          await load()
        },
      })
    },
    [load]
  )

  const handlePause = useCallback(
    (biz: Business) => {
      const nextStatus = biz.status === 'paused' ? 'active' : 'paused'
      const label = nextStatus === 'paused' ? '一時停止' : '再開'
      setConfirm({
        title: `「${biz.name}」を${label}しますか？`,
        confirmLabel: label,
        destructive: false,
        run: async () => {
          await api<Business>('PATCH', `/api/businesses/${encodeURIComponent(biz.id)}`, {
            status: nextStatus,
          })
          toast.success(`「${biz.name}」を${label}しました。`)
          await load()
        },
      })
    },
    [load]
  )

  const handleDelete = useCallback(
    (biz: Business) => {
      setConfirm({
        title: `「${biz.name}」を削除しますか？`,
        description: 'この操作は取り消せません。',
        confirmLabel: '削除する',
        destructive: true,
        run: async () => {
          await api<{ ok: boolean; deleted: boolean }>(
            'DELETE',
            `/api/businesses/${encodeURIComponent(biz.id)}`
          )
          toast.success(`「${biz.name}」を削除しました。`)
          if (outcomesId === biz.id) {
            setOutcomesId(null)
            setOutcomes(null)
          }
          await load()
        },
      })
    },
    [load, outcomesId]
  )

  return (
    <>
      <PageHeader
        title="事業"
        subtitle="複数の組織を集客→制作→収益化のルートで束ねた事業ポートフォリオ"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setShowCreate((v) => !v)}
            >
              <Plus size={14} />
              事業を作成
            </button>
            <RefreshButton onClick={() => void load()} busy={loading} />
          </div>
        }
      />

      <div className="page-content flex flex-col gap-4">
        {/* Create form */}
        {showCreate && (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2 font-semibold">
                <Plus size={16} />
                新規事業を作成
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">事業名 *</span>
                  <input
                    className="input"
                    placeholder="例: AIコンテンツ事業"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">加盟組織（カンマ区切り）</span>
                  <input
                    className="input"
                    placeholder="例: SNS Growth, Note Sales"
                    value={createOrgs}
                    onChange={(e) => setCreateOrgs(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">目的（任意）</span>
                  <input
                    className="input"
                    placeholder="例: 月10万円の収益化"
                    value={createPurpose}
                    onChange={(e) => setCreatePurpose(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-muted">KPI（カンマ区切り・任意）</span>
                  <input
                    className="input"
                    placeholder="例: revenue, reach"
                    value={createKpis}
                    onChange={(e) => setCreateKpis(e.target.value)}
                  />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={creating}
                  onClick={() => void handleCreate()}
                >
                  <Plus size={14} />
                  {creating ? '作成中…' : '作成'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowCreate(false)}
                >
                  キャンセル
                </button>
              </div>
            </div>
          </div>
        )}

        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void load()}
          loadingText="事業を読み込み中…"
          errorTitle="事業の読み込みに失敗しました"
          isEmpty={businesses.length === 0}
          emptyIcon={Building2}
          emptyTitle="事業がありません"
          emptyHint="「事業を作成」ボタンから最初の事業を登録できます。"
        >
          <div className="flex flex-col gap-4">
            {businesses.map((biz) => (
              <div key={biz.id} className="card">
                <div className="card-body flex flex-col gap-3">
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-start gap-2 min-w-0 flex-1">
                      <Building2 size={18} className="shrink-0 mt-0.5 text-muted" />
                      <div className="min-w-0">
                        <div className="font-semibold truncate">{biz.name}</div>
                        {biz.purpose ? (
                          <div className="text-sm text-muted">{biz.purpose}</div>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 flex-wrap">
                      <span className={`badge ${statusBadge(biz.status)}`}>
                        {statusLabel(biz.status)}
                      </span>
                    </div>
                  </div>

                  {/* Meta row */}
                  <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
                    <span>
                      <span className="font-medium text-fg">
                        {biz.member_orgs.length}
                      </span>{' '}
                      組織
                    </span>
                    <span>
                      <span className="font-medium text-fg">
                        {biz.handoff_routes.length}
                      </span>{' '}
                      ルート
                    </span>
                    {biz.kpis.length > 0 && (
                      <span>
                        KPI: <span className="font-medium text-fg">{biz.kpis.join(', ')}</span>
                      </span>
                    )}
                  </div>

                  {/* Handoff routes */}
                  {biz.handoff_routes.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-sm">
                      {biz.handoff_routes.map((r, i) => (
                        <span
                          key={i}
                          className="flex items-center gap-1 badge badge-neutral"
                        >
                          <span>{r.from_org}</span>
                          <ArrowRightLeft size={10} />
                          <span>{r.to_org}</span>
                          {r.kind ? (
                            <span className="text-muted">({r.kind})</span>
                          ) : null}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 flex-wrap border-t border-base pt-3">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleViewOutcomes(biz.id)}
                    >
                      {outcomesId === biz.id ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                      成果を見る
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleCompose(biz)}
                      title="保留中のハンドオフルートを実体化する"
                    >
                      <GitMerge size={14} />
                      ハンドオフを実体化
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => handlePause(biz)}
                    >
                      {biz.status === 'paused' ? '再開' : '一時停止'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => navigate('/handoffs')}
                    >
                      <ArrowRightLeft size={14} />
                      引き渡しを確認
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-red-500"
                      onClick={() => handleDelete(biz)}
                    >
                      <Trash2 size={14} />
                      削除
                    </button>
                  </div>

                  {/* Outcomes panel */}
                  {outcomesId === biz.id && (
                    <div className="rounded-xl border border-white/10 p-3 flex flex-col gap-3">
                      {outcomesLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted">
                          <div className="spinner" />
                          成果を読み込み中…
                        </div>
                      ) : outcomes ? (
                        <>
                          <div className="flex items-center gap-2 text-sm font-semibold">
                            <Target size={14} />
                            成果サマリー
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="flex flex-col gap-1">
                              <div className="metric-label flex items-center gap-1">
                                <Coins size={12} />
                                累計収益
                              </div>
                              <div className="text-lg font-bold">
                                ¥{formatNumber(num(outcomes.total_revenue))}
                              </div>
                            </div>
                            <div className="flex flex-col gap-1">
                              <div className="metric-label">累計リーチ</div>
                              <div className="text-lg font-bold">
                                {formatNumber(num(outcomes.total_reach))}
                              </div>
                            </div>
                            <div className="flex flex-col gap-1">
                              <div className="metric-label">イベント数</div>
                              <div className="text-lg font-bold">
                                {formatNumber(num(outcomes.event_count))}
                              </div>
                            </div>
                            <div className="flex flex-col gap-1">
                              <div className="metric-label">加盟組織</div>
                              <div className="text-lg font-bold">
                                {outcomes.member_orgs.length}
                              </div>
                            </div>
                          </div>
                          {Object.keys(outcomes.by_metric).length > 0 && (
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>メトリクス</th>
                                  <th className="text-right">合計</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(outcomes.by_metric).map(([metric, value]) => (
                                  <tr key={metric}>
                                    <td className="font-medium">{metric}</td>
                                    <td className="text-right">
                                      {formatNumber(num(value))}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </AsyncBoundary>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel}
        destructive={confirm?.destructive ?? true}
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </>
  )
}
