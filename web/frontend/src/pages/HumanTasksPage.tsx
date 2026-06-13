import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, RefreshCw, UserCheck } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type HumanTask = {
  task_id: string
  title: string
  description: string
  kind: string
  org_name: string
  status: string
}

type HumanTasksResponse = {
  items: HumanTask[]
  open: number
  total: number
}

export function HumanTasksPage() {
  const [tasks, setTasks] = useState<HumanTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<HumanTasksResponse>('GET', '/api/human-tasks?status=open')
      setTasks(res.items)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '人間タスクの読み込みに失敗しました。'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const complete = useCallback(
    async (taskId: string) => {
      setBusy(taskId)
      try {
        await api('POST', `/api/human-tasks/${encodeURIComponent(taskId)}/complete`)
        toast.success('完了にしました。')
        await load()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '完了に失敗しました。')
      } finally {
        setBusy(null)
      }
    },
    [load]
  )

  return (
    <>
      <header className="page-header">
        <div className="page-title">あなたのタスク（Human Member）</div>
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
              <div className="text-muted">人間タスクを読み込み中…</div>
            </div>
          </div>
        ) : error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : tasks.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <UserCheck className="empty-state-icon" size={28} />
                <h3>未対応の人間タスクはありません</h3>
                <p>
                  Pantheon は AI で出来る作業を進め、人間にしかできないこと（アカウント作成・高リスク承認・
                  実投稿の最終確認など）だけをここに積みます。
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              {tasks.map((t) => (
                <div key={t.task_id} className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="badge badge-neutral">{t.kind}</span>
                      {t.org_name ? <span className="text-muted text-sm">{t.org_name}</span> : null}
                      <span className="font-medium truncate">{t.title}</span>
                    </div>
                    {t.description ? <div className="text-sm text-muted mt-1">{t.description}</div> : null}
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={busy === t.task_id}
                    onClick={() => void complete(t.task_id)}
                  >
                    <CheckCircle size={14} />
                    完了
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
