import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle,
  Eye,
  Inbox as InboxIcon,
  Lightbulb,
  RefreshCw,
  Send,
  Trash2,
  UserCheck,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { priorityLabel } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'

type InboxKind = 'proposal' | 'handoff' | 'publish' | 'human_task'

type InboxItem = {
  kind: InboxKind
  id: string
  org_name: string
  title: string
  category: string
  priority: string
  revenue_impact?: number
  platform?: string
  scheduled_at?: string | null
  ref?: string
  created_at?: string
  route: string
  status?: string
}

type InboxCounts = {
  proposal: number
  handoff: number
  publish: number
  human_task: number
  total: number
}

type InboxResponse = {
  items: InboxItem[]
  counts: InboxCounts
}

const KIND_FILTERS = ['all', 'publish', 'proposal', 'handoff', 'human_task'] as const
type KindFilter = (typeof KIND_FILTERS)[number]

function kindLabel(kind: InboxKind): string {
  if (kind === 'proposal') return '改善提案'
  if (kind === 'handoff') return '引き渡し'
  if (kind === 'human_task') return 'あなたのタスク'
  return '投稿待ち'
}

function kindBadge(kind: InboxKind): string {
  if (kind === 'proposal') return 'badge-blue'
  if (kind === 'handoff') return 'badge-neutral'
  if (kind === 'human_task') return 'badge-yellow'
  return 'badge-green'
}

function priorityBadge(priority: string): string {
  if (priority === 'high' || priority === 'critical') return 'badge-red'
  if (priority === 'low') return 'badge-neutral'
  return 'badge-yellow'
}

function KindIcon({ kind }: { kind: InboxKind }) {
  if (kind === 'proposal') return <Lightbulb size={14} />
  if (kind === 'handoff') return <ArrowRightLeft size={14} />
  if (kind === 'human_task') return <UserCheck size={14} />
  return <Send size={14} />
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

export function InboxPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<InboxItem[]>([])
  const [counts, setCounts] = useState<InboxCounts>({
    proposal: 0,
    handoff: 0,
    publish: 0,
    human_task: 0,
    total: 0,
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [actionId, setActionId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const { events } = usePlatformUpdates()

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const data = await api<InboxResponse>('GET', '/api/inbox')
      setItems(data.items)
      setCounts(data.counts)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'インボックスの読み込みに失敗しました。'
      setItems([])
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const latest = events[0]
    if (
      latest?.type &&
      (latest.type.startsWith('publish') ||
        latest.type.startsWith('proposal') ||
        latest.type.startsWith('handoff') ||
        latest.type.startsWith('human'))
    ) {
      void load(true)
    }
  }, [events, load])

  const visibleItems = useMemo(
    () => (kindFilter === 'all' ? items : items.filter((item) => item.kind === kindFilter)),
    [items, kindFilter],
  )

  const runAction = async (key: string, fn: () => Promise<void>, successMsg: string, reload = true) => {
    setActionId(key)
    try {
      await fn()
      toast.success(successMsg)
      if (reload) await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  // ConfirmDialog 経由の破壊/外部送信操作用。失敗時は再 throw してダイアログを開いたままにする。
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const approveItem = (item: InboxItem) => {
    const key = `${item.kind}:${item.id}`
    if (item.kind === 'proposal') {
      void runAction(
        key,
        async () => {
          await api('POST', `/api/proposals/${encodeURIComponent(item.org_name)}/${encodeURIComponent(item.id)}/approve`)
        },
        '提案を承認しました。',
      )
    } else if (item.kind === 'handoff') {
      void runAction(
        key,
        async () => {
          await api('POST', `/api/handoffs/${encodeURIComponent(item.id)}/approve`, { draft: true })
        },
        '引き渡しを承認し、本文ドラフトを生成しました。',
      )
    } else if (item.kind === 'human_task') {
      // 人間タスクの完了（不可逆）— 確認ゲートを通す（C003/C006）。
      setConfirm({
        title: 'タスクを完了にしますか？',
        description: (
          <>
            「{item.title}」を完了にします。<strong>この操作は取り消せません。</strong>
          </>
        ),
        confirmLabel: '完了にする',
        run: () =>
          directRun(
            () => api('POST', `/api/human-tasks/${encodeURIComponent(item.id)}/complete`),
            'タスクを完了にしました。',
          ),
      })
    } else {
      // 外部への実投稿（取り消し不能）— 必ず確認ゲートを通す（C001 / PUB-AUTO 人手ゲート）。
      setConfirm({
        title: '外部に投稿しますか？',
        description: (
          <>
            「{item.title}」を {item.platform ?? '外部'} に公開します。
            <strong>この操作は取り消せません。</strong>
            {item.scheduled_at ? <>（予約: {item.scheduled_at}）</> : null}
          </>
        ),
        confirmLabel: '投稿する',
        run: () =>
          directRun(
            () => api('POST', `/api/publish-jobs/${encodeURIComponent(item.id)}/run`),
            '投稿を実行しました。',
          ),
      })
    }
  }

  const rejectItem = (item: InboxItem) => {
    const key = `${item.kind}:${item.id}`
    if (item.kind === 'proposal') {
      void runAction(
        key,
        async () => {
          await api('POST', `/api/proposals/${encodeURIComponent(item.org_name)}/${encodeURIComponent(item.id)}/reject`)
        },
        '提案を却下しました。',
      )
    } else if (item.kind === 'handoff') {
      void runAction(
        key,
        async () => {
          await api('POST', `/api/handoffs/${encodeURIComponent(item.id)}/reject`)
        },
        '引き渡しを却下しました。',
      )
    } else {
      // 投稿ジョブの削除（復元不能）— 確認ゲートを通す（C001/C002）。
      setConfirm({
        title: '投稿ジョブを取り消しますか？',
        description: (
          <>
            「{item.title}」の投稿ジョブを削除します。<strong>取り消すと復元できません。</strong>
          </>
        ),
        confirmLabel: '取り消す',
        run: () =>
          directRun(
            () => api('DELETE', `/api/publish-jobs/${encodeURIComponent(item.id)}`),
            '投稿ジョブを取り消しました。',
          ),
      })
    }
  }

  const previewPublish = (item: InboxItem) => {
    void runAction(
      `preview:${item.id}`,
      async () => {
        await api('POST', `/api/publish-jobs/${encodeURIComponent(item.id)}/run?dry_run=true`)
      },
      'プレビュー（dry-run）を実行しました。投稿はしていません。',
      false,
    )
  }

  const confirmPublish = (item: InboxItem) => {
    // 公開の確定（外部反映の確定・取り消し不能）— 確認ゲートを通す（C001）。
    setConfirm({
      title: '公開を確定しますか？',
      description: (
        <>
          「{item.title}」の公開を確定します。<strong>この操作は取り消せません。</strong>
        </>
      ),
      confirmLabel: '公開を確定',
      run: () =>
        directRun(
          () => api('POST', `/api/publish-jobs/${encodeURIComponent(item.id)}/confirm`),
          '公開を確認しました。',
        ),
    })
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">承認インボックス</div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          {KIND_FILTERS.map((filter) => {
            const count = filter === 'all' ? counts.total : counts[filter]
            const label = filter === 'all' ? 'すべて' : kindLabel(filter)
            return (
              <button
                key={filter}
                type="button"
                className={`btn btn-sm ${kindFilter === filter ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setKindFilter(filter)}
              >
                {label}
                <span className="badge badge-neutral">{count}</span>
              </button>
            )
          })}
        </div>

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">インボックスを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>インボックスの読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && visibleItems.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <InboxIcon className="empty-state-icon" size={28} />
                <h3>承認待ちはありません</h3>
                <p>定期実行で下書きや投稿が溜まると、ここで承認するだけで公開まで進みます。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error
          ? visibleItems.map((item) => {
              const key = `${item.kind}:${item.id}`
              const isHandedOff = item.kind === 'publish' && item.status === 'handed_off'
              const busy = actionId === key || actionId === `preview:${item.id}` || actionId === `confirm:${item.id}`
              return (
                <div key={key} className="proposal-card">
                  <div className="proposal-header">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className={`badge ${kindBadge(item.kind)} flex items-center gap-1`}>
                          <KindIcon kind={item.kind} />
                          {kindLabel(item.kind)}
                        </span>
                        {isHandedOff ? (
                          <span className="badge badge-yellow flex items-center gap-1">
                            <CheckCircle size={12} />
                            公開確認待ち
                          </span>
                        ) : null}
                        <div className="font-semibold truncate">{item.title}</div>
                        {(item.revenue_impact ?? 0) >= 2 ? (
                          <span className="badge badge-green">収益</span>
                        ) : null}
                        <span className={`badge ${priorityBadge(item.priority)}`}>
                          {priorityLabel(item.priority)}
                        </span>
                        {item.platform ? <span className="badge badge-neutral">{item.platform}</span> : null}
                      </div>
                      <div className="text-sm text-fg2">
                        {item.org_name || '—'}
                        {item.scheduled_at ? ` ・ 予約: ${formatDateTime(item.scheduled_at)}` : ''}
                        {item.kind === 'human_task' && item.created_at
                          ? ` ・ 作成: ${formatDateTime(item.created_at)}`
                          : ''}
                      </div>
                    </div>
                  </div>
                  <div className="proposal-actions">
                    {isHandedOff ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm text-green"
                        onClick={() => confirmPublish(item)}
                        disabled={busy}
                      >
                        <CheckCircle size={14} />
                        公開を確認
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm text-green"
                          onClick={() => approveItem(item)}
                          disabled={busy}
                        >
                          <CheckCircle size={14} />
                          {item.kind === 'publish' ? '投稿' : item.kind === 'human_task' ? '完了' : '承認'}
                        </button>
                        {item.kind === 'publish' ? (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => previewPublish(item)}
                            disabled={busy}
                            title="dry-run。外部には投稿しません。"
                          >
                            <Eye size={14} />
                            プレビュー
                          </button>
                        ) : null}
                      </>
                    )}
                    {item.kind !== 'human_task' ? (
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => rejectItem(item)}
                        disabled={busy}
                      >
                        {item.kind === 'publish' ? <Trash2 size={14} /> : <XCircle size={14} />}
                        {item.kind === 'publish' ? '取消' : '却下'}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => navigate(item.route)}
                    >
                      開く
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
