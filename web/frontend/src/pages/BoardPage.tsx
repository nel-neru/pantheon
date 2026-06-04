import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Plus, RefreshCw, X } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

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

type Column = {
  key: string
  label: string
  statuses: string[]
  badge: string
}

const columns: Column[] = [
  { key: 'queued', label: 'キュー', statuses: ['pending'], badge: 'badge-yellow' },
  { key: 'running', label: '実行中', statuses: ['running'], badge: 'badge-blue' },
  { key: 'review', label: 'レビュー', statuses: ['failed'], badge: 'badge-red' },
  { key: 'done', label: '完了', statuses: ['done', 'cancelled'], badge: 'badge-green' },
]

export function BoardPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ description: '', org_name: '', task_type: 'manual' })

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<TasksResponse>('GET', '/api/tasks?limit=200')
      setTasks(res.tasks)
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '作業ボードの読み込みに失敗しました。'
      setTasks([])
      setLoadError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleCreate = async () => {
    if (!form.description.trim() || !form.org_name.trim()) {
      toast.error('説明と組織名を入力してください。')
      return
    }
    setCreating(true)
    try {
      await api('POST', '/api/tasks', {
        task_type: form.task_type || 'manual',
        org_name: form.org_name,
        description: form.description,
        priority: 5,
      })
      toast.success('タスクを起票しました。')
      setForm({ description: '', org_name: '', task_type: 'manual' })
      setShowForm(false)
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'タスクの起票に失敗しました。')
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = async (id: string) => {
    try {
      await api('DELETE', `/api/tasks/${encodeURIComponent(id)}`)
      toast.success('タスクをキャンセルしました。')
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'タスクのキャンセルに失敗しました。')
    }
  }

  const grouped = useMemo(() => {
    const map: Record<string, Task[]> = {}
    for (const column of columns) {
      map[column.key] = tasks.filter((task) => column.statuses.includes(task.status))
    }
    return map
  }, [tasks])

  return (
    <>
      <header className="page-header">
        <div className="page-title">作業ボード</div>
        <div className="page-actions">
          <span className="badge badge-neutral">{tasks.length} タスク</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void loadData()} aria-label="再読み込み">
            <RefreshCw size={14} />
            更新
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowForm((value) => !value)}>
            <Plus size={14} />
            新規タスク
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {showForm ? (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <input
                className="input"
                placeholder="タスクの説明"
                value={form.description}
                onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                aria-label="タスクの説明"
              />
              <div className="flex items-center gap-3 flex-wrap">
                <input
                  className="input"
                  style={{ width: 'auto', minWidth: '180px' }}
                  placeholder="組織名"
                  value={form.org_name}
                  onChange={(event) => setForm((prev) => ({ ...prev, org_name: event.target.value }))}
                  aria-label="組織名"
                />
                <input
                  className="input"
                  style={{ width: 'auto', minWidth: '140px' }}
                  placeholder="種別 (manual)"
                  value={form.task_type}
                  onChange={(event) => setForm((prev) => ({ ...prev, task_type: event.target.value }))}
                  aria-label="種別"
                />
                <button type="button" className="btn btn-primary" onClick={handleCreate} disabled={creating}>
                  {creating ? '起票中…' : '起票'}
                </button>
              </div>
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
                <AlertTriangle className="empty-state-icon" size={28} />
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
                    <div className="text-muted text-sm">なし</div>
                  ) : (
                    grouped[column.key].map((task) => (
                      <div key={task.id} className="board-card">
                        <div className="flex items-start justify-between gap-2">
                          <div className="font-semibold text-sm">{task.description}</div>
                          {task.status === 'pending' || task.status === 'running' ? (
                            <button
                              type="button"
                              className="btn btn-ghost btn-icon btn-sm"
                              onClick={() => void handleCancel(task.id)}
                              aria-label="タスクをキャンセル"
                            >
                              <X size={13} />
                            </button>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap mt-2">
                          <span className="badge badge-neutral text-xs">{task.type}</span>
                          <span className="text-xs text-muted">{task.org_name}</span>
                        </div>
                        {task.error ? <div className="text-xs text-red mt-1">{task.error}</div> : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </>
  )
}
