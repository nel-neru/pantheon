import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ClipboardList, Plus, RefreshCw, X } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { formatDateTime } from '@/lib/utils'

type Task = {
  id: string
  type: string
  org_name: string
  description: string
  status: string
  priority: number
  created_at?: string
  error?: string | null
}

type TasksResponse = {
  tasks: Task[]
  stats?: Record<string, number>
}

type OrgItem = {
  name: string
}

type Column = {
  key: string
  label: string
  statuses: string[]
  badge: string
}

const TASK_TYPES = ['manual', 'analysis', 'improvement', 'content'] as const
type TaskType = (typeof TASK_TYPES)[number]

const columns: Column[] = [
  { key: 'queued', label: 'キュー', statuses: ['pending'], badge: 'badge-yellow' },
  { key: 'running', label: '実行中', statuses: ['running'], badge: 'badge-blue' },
  { key: 'failed', label: '失敗', statuses: ['failed'], badge: 'badge-red' },
  { key: 'done', label: '完了', statuses: ['done', 'cancelled'], badge: 'badge-green' },
]

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

export function BoardPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [orgs, setOrgs] = useState<OrgItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<{ description: string; org_name: string; task_type: TaskType }>({
    description: '',
    org_name: '',
    task_type: 'manual',
  })
  const [totalCount, setTotalCount] = useState<number | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const descRef = useRef<HTMLTextAreaElement>(null)

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [res, orgRes] = await Promise.all([
        api<TasksResponse>('GET', '/api/tasks?limit=200'),
        api<OrgItem[]>('GET', '/api/organizations').catch(() => [] as OrgItem[]),
      ])
      setTasks(res.tasks)
      setTotalCount(res.stats?.total ?? null)
      setOrgs(orgRes)
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '作業ボードの読み込みに失敗しました。'
      if (!quiet) {
        setTasks([])
        setLoadError(message)
      }
      toast.error(message)
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // フォームを開いたとき説明欄にフォーカス
  useEffect(() => {
    if (showForm) {
      setTimeout(() => descRef.current?.focus(), 0)
    }
  }, [showForm])

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!form.description.trim()) {
      toast.error('タスクの説明を入力してください。')
      return
    }
    if (!form.org_name) {
      toast.error('組織を選択してください。')
      return
    }
    setCreating(true)
    try {
      await api('POST', '/api/tasks', {
        task_type: form.task_type,
        org_name: form.org_name,
        description: form.description,
        priority: 5,
      })
      toast.success('タスクを起票しました。')
      setForm({ description: '', org_name: form.org_name, task_type: form.task_type })
      setShowForm(false)
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'タスクの起票に失敗しました。')
    } finally {
      setCreating(false)
    }
  }

  const requestCancel = (task: Task) => {
    setConfirm({
      title: 'タスクをキャンセルしますか？',
      description: (
        <>
          「{task.description}」をキャンセルします。<strong>この操作は取り消せません。</strong>
        </>
      ),
      confirmLabel: 'キャンセルする',
      run: async () => {
        await api('DELETE', `/api/tasks/${encodeURIComponent(task.id)}`)
        toast.success('タスクをキャンセルしました。')
        await loadData(true)
      },
    })
  }

  const grouped = useMemo(() => {
    const map: Record<string, Task[]> = {}
    for (const column of columns) {
      map[column.key] = tasks.filter((task) => column.statuses.includes(task.status))
    }
    return map
  }, [tasks])

  const displayTotal = totalCount ?? tasks.length
  const displayCount = tasks.length

  return (
    <>
      <header className="page-header">
        <div className="page-title">作業ボード</div>
        <div className="page-actions">
          {displayTotal > displayCount ? (
            <span className="badge badge-neutral text-xs">
              全 {displayTotal} 件中 {displayCount} 件表示
            </span>
          ) : (
            <span className="badge badge-neutral text-xs">{displayTotal} 件</span>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void loadData(true)}
            disabled={loading}
            aria-label="再読み込み"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            更新
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowForm((v) => !v)}>
            <Plus size={14} />
            新規タスク
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {showForm ? (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <form onSubmit={(e) => void handleCreate(e)} className="flex flex-col gap-3">
                <textarea
                  ref={descRef}
                  className="input"
                  placeholder="タスクの説明"
                  rows={3}
                  required
                  value={form.description}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, description: event.target.value }))
                  }
                  aria-label="タスクの説明"
                />
                <div className="flex items-center gap-3 flex-wrap">
                  <select
                    className="input min-w-[180px] w-auto"
                    value={form.org_name}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, org_name: event.target.value }))
                    }
                    aria-label="組織名"
                    required
                  >
                    <option value="">組織を選択…</option>
                    {orgs.map((org) => (
                      <option key={org.name} value={org.name}>
                        {org.name}
                      </option>
                    ))}
                  </select>
                  <select
                    className="input min-w-[140px] w-auto"
                    value={form.task_type}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        task_type: event.target.value as TaskType,
                      }))
                    }
                    aria-label="種別"
                  >
                    {TASK_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <button type="submit" className="btn btn-primary" disabled={creating}>
                    {creating ? '起票中…' : '起票'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setShowForm(false)}
                  >
                    閉じる
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">作業ボードを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && loadError ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <ClipboardList className="empty-state-icon" size={28} />
                <h3>作業ボードの読み込みに失敗しました</h3>
                <p>{loadError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadData()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !loadError ? (
          <div className="board-grid">
            {columns.map((column) => (
              <div key={column.key} className="board-column card">
                <div className="card-header">
                  <div className="card-title flex items-center gap-2">
                    {column.label}
                    <span className={`badge ${column.badge}`}>{grouped[column.key].length}</span>
                  </div>
                </div>
                <div className="card-body flex flex-col gap-2">
                  {grouped[column.key].length === 0 ? (
                    <div className="text-muted text-sm">
                      {column.key === 'queued'
                        ? 'タスクがありません — 新規タスクを起票'
                        : '該当なし'}
                    </div>
                  ) : (
                    grouped[column.key].map((task) => (
                      <div key={task.id} className="board-card">
                        <div className="flex items-start justify-between gap-2">
                          <div className="font-semibold text-sm">{task.description}</div>
                          {task.status === 'pending' ? (
                            <button
                              type="button"
                              className="btn btn-ghost btn-icon btn-sm"
                              onClick={() => requestCancel(task)}
                              aria-label="タスクをキャンセル"
                            >
                              <X size={13} />
                            </button>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap mt-2">
                          <span className="badge badge-neutral text-xs">{task.type}</span>
                          <span className="text-xs text-muted">{task.org_name}</span>
                          {task.status === 'cancelled' ? (
                            <span className="badge badge-neutral text-xs">キャンセル済</span>
                          ) : null}
                          {task.created_at ? (
                            <span className="text-xs text-muted">{formatDateTime(task.created_at)}</span>
                          ) : null}
                          {task.priority != null ? (
                            <span className="text-xs text-muted">優先度 {task.priority}</span>
                          ) : null}
                        </div>
                        {task.error ? (
                          <div className="text-xs text-red mt-1 line-clamp-3" title={task.error}>
                            {task.error}
                          </div>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : null}
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
