import { useCallback, useEffect, useMemo, useState } from 'react'
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
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'

type InboxKind = 'proposal' | 'handoff' | 'publish'

type InboxItem = {
  kind: InboxKind
  id: string
  org_name: string
  title: string
  category: string
  priority: string
  platform?: string
  scheduled_at?: string | null
  route: string
  status?: string
}

type InboxCounts = {
  proposal: number
  handoff: number
  publish: number
  total: number
}

type InboxResponse = {
  items: InboxItem[]
  counts: InboxCounts
}

const KIND_FILTERS = ['all', 'publish', 'proposal', 'handoff'] as const
type KindFilter = (typeof KIND_FILTERS)[number]

function kindLabel(kind: InboxKind): string {
  if (kind === 'proposal') return '改善提案'
  if (kind === 'handoff') return '引き渡し'
  return '投稿待ち'
}

function kindBadge(kind: InboxKind): string {
  if (kind === 'proposal') return 'badge-blue'
  if (kind === 'handoff') return 'badge-neutral'
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
  return <Send size={14} />
}

export function InboxPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<InboxItem[]>([])
  const [counts, setCounts] = useState<InboxCounts>({ proposal: 0, handoff: 0, publish: 0, total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [actionId, setActionId] = useState<string | null>(null)
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
        latest.type.startsWith('handoff'))
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
    } else {
      void runAction(
        key,
        async () => {
          await api('POST', `/api/publish-jobs/${encodeURIComponent(item.id)}/run`)
        },
        '投稿を実行しました。',
      )
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
      void runAction(
        key,
        async () => {
          await api('DELETE', `/api/publish-jobs/${encodeURIComponent(item.id)}`)
        },
        '投稿ジョブを取り消しました。',
      )
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
    void runAction(
      `confirm:${item.id}`,
      async () => {
        await api('POST', `/api/publish-jobs/${encodeURIComponent(item.id)}/confirm`)
      },
      '公開を確認しました。',
    )
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
            const count =
              filter === 'all'
                ? counts.total
                : filter === 'proposal'
                  ? counts.proposal
                  : filter === 'handoff'
                    ? counts.handoff
                    : counts.publish
            return (
              <button
                key={filter}
                type="button"
                className={`btn btn-sm ${kindFilter === filter ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setKindFilter(filter)}
              >
                {filter === 'all'
                  ? 'すべて'
                  : filter === 'proposal'
                    ? '改善提案'
                    : filter === 'handoff'
                      ? '引き渡し'
                      : '投稿待ち'}
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
                        <span className={`badge ${priorityBadge(item.priority)}`}>{item.priority}</span>
                        {item.platform ? <span className="badge badge-neutral">{item.platform}</span> : null}
                      </div>
                      <div className="text-sm text-fg2">
                        {item.org_name || '—'}
                        {item.scheduled_at ? ` ・ 予約: ${item.scheduled_at}` : ''}
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
                          {item.kind === 'publish' ? '投稿' : '承認'}
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
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => rejectItem(item)}
                      disabled={busy}
                    >
                      {item.kind === 'publish' ? <Trash2 size={14} /> : <XCircle size={14} />}
                      {item.kind === 'publish' ? '取消' : '却下'}
                    </button>
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
    </>
  )
}
