import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Boxes, FileText, Play, RefreshCw, Square, Terminal } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type Surface = {
  id: string
  title: string
  agent_id: string
  role?: string
  status: string
  exit_code?: number | null
  pty_id?: string | null
  workspace_id?: string | null
  log_path?: string | null
}

type SessionRecord = {
  id: string
  name: string
  driver: string
  status: string
  created_at: string
  workspace: { id?: string; name?: string }
  surfaces: Surface[]
}

type RuntimeStatus = {
  claude: { available: boolean; binary?: string | null }
  wmux: { running: boolean; state: string }
  driver: string
}

function statusBadge(status: string) {
  if (status === 'running') return 'badge-blue'
  if (status === 'done' || status === 'completed' || status === 'connected') return 'badge-green'
  if (status === 'failed' || status === 'error') return 'badge-red'
  if (status === 'awaiting-approval' || status === 'pending') return 'badge-yellow'
  return 'badge-neutral'
}

function wmuxLabel(state: string) {
  if (state === 'connected') return 'wmux 接続中'
  if (state === 'awaiting-approval') return 'wmux 承認待ち'
  if (state === 'not-running') return 'wmux 未起動'
  return 'wmux エラー'
}

export function SessionsPage() {
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [selected, setSelected] = useState<{ sessionId: string; agentId: string; title: string } | null>(null)
  const [logText, setLogText] = useState<string>('')
  const [logLoading, setLogLoading] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [sessionResult, runtimeResult] = await Promise.allSettled([
        api<{ sessions: SessionRecord[] }>('GET', '/api/sessions'),
        api<RuntimeStatus>('GET', '/api/sessions/runtime'),
      ])
      if (sessionResult.status === 'rejected') {
        throw sessionResult.reason
      }
      setSessions(sessionResult.value.sessions)
      setRuntime(runtimeResult.status === 'fulfilled' ? runtimeResult.value : null)
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'セッションの読み込みに失敗しました。'
      setSessions([])
      setRuntime(null)
      setLoadError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleStartDemo = async () => {
    setStarting(true)
    try {
      const rec = await api<SessionRecord>('POST', '/api/sessions', { name: 'Demo' })
      toast.success(`セッション開始: ${rec.name}（${rec.driver}）`)
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'セッションの開始に失敗しました。')
    } finally {
      setStarting(false)
    }
  }

  const handleStop = async (sessionId: string) => {
    try {
      await api('POST', `/api/sessions/${encodeURIComponent(sessionId)}/stop`)
      toast.success('セッションを停止しました。')
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'セッションの停止に失敗しました。')
    }
  }

  const openLog = async (sessionId: string, agentId: string, title: string) => {
    setSelected({ sessionId, agentId, title })
    setLogLoading(true)
    setLogText('')
    try {
      const res = await api<{ log: string }>(
        'GET',
        `/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(agentId)}/log`,
      )
      setLogText(res.log || '(まだ出力がありません)')
    } catch (error) {
      setLogText(error instanceof Error ? error.message : 'ログの取得に失敗しました。')
    } finally {
      setLogLoading(false)
    }
  }

  const totalAgents = useMemo(
    () => sessions.reduce((total, session) => total + session.surfaces.length, 0),
    [sessions],
  )

  return (
    <>
      <header className="page-header">
        <div className="page-title">セッション</div>
        <div className="page-actions">
          <span className="badge badge-neutral">{sessions.length} セッション</span>
          <span className="badge badge-blue">{totalAgents} エージェント</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void loadData()} aria-label="再読み込み">
            <RefreshCw size={14} />
            更新
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={handleStartDemo} disabled={starting}>
            <Play size={14} />
            {starting ? '開始中…' : 'デモセッション開始'}
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {runtime ? (
          <div className="card">
            <div className="card-body flex items-center gap-3 flex-wrap">
              <span className={`badge ${statusBadge(runtime.claude.available ? 'done' : 'failed')}`}>
                {runtime.claude.available ? 'claude CLI 検出' : 'claude CLI 未検出'}
              </span>
              <span className={`badge ${statusBadge(runtime.wmux.state)}`}>{wmuxLabel(runtime.wmux.state)}</span>
              <span className="badge badge-neutral">driver: {runtime.driver}</span>
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">セッションを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && loadError ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>セッションの読み込みに失敗しました</h3>
                <p>{loadError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadData()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !loadError && sessions.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <Boxes className="empty-state-icon" size={28} />
                <h3>セッションがありません</h3>
                <p>「デモセッション開始」を押すと、wmux 上にエージェントのタブが自動生成されます。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !loadError && sessions.length > 0 ? (
          <div className="grid-2">
            <div className="flex flex-col gap-4">
              {sessions.map((session) => (
                <div key={session.id} className="card">
                  <div className="card-header">
                    <div>
                      <div className="card-title">{session.name}</div>
                      <div className="card-description">
                        {session.driver} · {session.id}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`badge ${statusBadge(session.status)}`}>{session.status}</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => void handleStop(session.id)}
                        aria-label={`${session.name} を停止`}
                      >
                        <Square size={13} />
                        停止
                      </button>
                    </div>
                  </div>
                  <div className="card-body">
                    {session.surfaces.length === 0 ? (
                      <div className="text-muted text-sm">エージェントがありません。</div>
                    ) : (
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>エージェント</th>
                              <th>状態</th>
                              <th>終了コード</th>
                              <th>ログ</th>
                            </tr>
                          </thead>
                          <tbody>
                            {session.surfaces.map((surface) => (
                              <tr key={surface.id}>
                                <td>
                                  <div className="font-semibold">{surface.title}</div>
                                  <div className="text-xs text-muted">{surface.agent_id}</div>
                                </td>
                                <td>
                                  <span className={`badge ${statusBadge(surface.status)}`}>{surface.status}</span>
                                </td>
                                <td className="mono text-sm">
                                  {surface.exit_code === null || surface.exit_code === undefined ? '—' : surface.exit_code}
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="btn btn-ghost btn-sm"
                                    onClick={() => void openLog(session.id, surface.agent_id, surface.title)}
                                  >
                                    <FileText size={13} />
                                    表示
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">エージェントログ</div>
                  <div className="card-description">各エージェントの claude 出力（stream-json）を確認できます。</div>
                </div>
              </div>
              <div className="card-body">
                {selected ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold">{selected.title}</div>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>
                        閉じる
                      </button>
                    </div>
                    {logLoading ? (
                      <div className="flex items-center gap-3">
                        <div className="spinner" />
                        <div className="text-muted">ログを取得中…</div>
                      </div>
                    ) : (
                      <pre className="progress-log">{logText}</pre>
                    )}
                  </div>
                ) : (
                  <div className="empty-state" style={{ padding: '24px' }}>
                    <Terminal className="empty-state-icon" size={24} />
                    <h3>ログを選択してください</h3>
                    <p>「表示」ボタンからエージェントの出力ログを確認できます。</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  )
}
