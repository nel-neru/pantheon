import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Boxes, ClipboardCopy, ExternalLink, FileText, RefreshCw, Square, Terminal } from 'lucide-react'
import { toast } from 'sonner'

import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { statusLabel, statusBadge } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'

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

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

// wmux 状態の日本語ラベルとバッジ配色
type WmuxInfo = { label: string; badge: string }
function wmuxInfo(state: string): WmuxInfo {
  if (state === 'connected') return { label: 'wmux 接続中', badge: 'badge-green' }
  if (state === 'awaiting-approval') return { label: 'wmux 承認待ち', badge: 'badge-yellow' }
  if (state === 'not-running') return { label: 'wmux 未起動', badge: 'badge-neutral' }
  return { label: 'wmux エラー', badge: 'badge-red' }
}

export function SessionsPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [runtime, setRuntime] = useState<RuntimeStatus | null | 'error'>('error')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ sessionId: string; agentId: string; title: string } | null>(null)
  const [logText, setLogText] = useState<string>('')
  const [logError, setLogError] = useState<string | null>(null)
  const [logLoading, setLogLoading] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [stoppingId, setStoppingId] = useState<string | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const { events } = usePlatformUpdates()

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [sessionResult, runtimeResult] = await Promise.allSettled([
        api<{ sessions: SessionRecord[] }>('GET', '/api/sessions'),
        api<RuntimeStatus>('GET', '/api/sessions/runtime'),
      ])
      if (sessionResult.status === 'rejected') {
        throw sessionResult.reason
      }
      setSessions(sessionResult.value.sessions)
      setRuntime(runtimeResult.status === 'fulfilled' ? runtimeResult.value : 'error')
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'セッションの読み込みに失敗しました。'
      if (!quiet) {
        setSessions([])
        setRuntime('error')
        setLoadError(message)
        // 初回失敗のみ toast（再試行は画面内エラー表示で対応）
        toast.error(message)
      }
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // WS セッション系イベントで静かに再取得してライブ監視（ポーリング不要）
  useEffect(() => {
    const latest = events[0]
    if (latest?.type && latest.type.startsWith('session')) {
      void loadData(true)
    }
  }, [events, loadData])

  // ログ再取得: 選択中エージェントに WS セッションイベントが届いたら追従
  const fetchLog = useCallback(async (sessionId: string, agentId: string) => {
    setLogLoading(true)
    setLogError(null)
    try {
      const res = await api<{ log: string }>(
        'GET',
        `/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(agentId)}/log`,
      )
      setLogText(res.log || '')
    } catch (error) {
      setLogError(error instanceof Error ? error.message : 'ログの取得に失敗しました。')
      setLogText('')
    } finally {
      setLogLoading(false)
    }
  }, [])

  // WS イベントでログも追従（ライブ監視の実現）
  useEffect(() => {
    const latest = events[0]
    if (selected && latest?.type && latest.type.startsWith('session')) {
      void fetchLog(selected.sessionId, selected.agentId)
    }
  }, [events, selected, fetchLog])

  // 自動スクロール：ログ更新時に末尾追従
  useEffect(() => {
    if (logText && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logText])

  // loadData で sessions が更新されたとき、選択中セッションが消えていたらクリア
  useEffect(() => {
    if (selected) {
      const sessionExists = sessions.some((s) => s.id === selected.sessionId)
      if (!sessionExists) {
        setSelected(null)
        setLogText('')
        setLogError(null)
      }
    }
  }, [sessions, selected])

  const openLog = (sessionId: string, agentId: string, title: string) => {
    setSelected({ sessionId, agentId, title })
    void fetchLog(sessionId, agentId)
  }

  // ConfirmDialog 経由: 失敗を再 throw してダイアログを開いたままにする
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
      await loadData()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const handleStopClick = (session: SessionRecord) => {
    const isDone = session.status === 'done' || session.status === 'completed' || session.status === 'failed'
    if (isDone) return
    setConfirm({
      title: `${session.name} を停止しますか？`,
      description: (
        <>
          稼働中のエージェント群が停止されます。<strong>この操作は取り消せません。</strong>
        </>
      ),
      confirmLabel: '停止する',
      run: async () => {
        setStoppingId(session.id)
        try {
          await directRun(
            () => api('POST', `/api/sessions/${encodeURIComponent(session.id)}/stop`),
            'セッションを停止しました。',
          )
        } finally {
          setStoppingId(null)
        }
      },
    })
  }

  const copyToClipboard = (text: string) => {
    void navigator.clipboard.writeText(text).then(() => toast.success('コピーしました。'))
  }

  const totalAgents = useMemo(
    () => sessions.reduce((total, session) => total + session.surfaces.length, 0),
    [sessions],
  )

  const runtimeData = runtime !== 'error' ? runtime : null
  const runtimeFailed = runtime === 'error'

  return (
    <>
      <header className="page-header">
        <div className="page-title">セッション</div>
        <div className="page-actions">
          <span className="badge badge-neutral">{sessions.length} セッション</span>
          <span className="badge badge-blue">{totalAgents} エージェント</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void loadData()}
            disabled={loading}
            aria-label="再読み込み"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {/* ランタイムステータスカード: 常時表示（失敗時も退行を可視化） */}
        <div className="card">
          <div className="card-body flex items-center gap-3 flex-wrap">
            {runtimeFailed && !runtimeData ? (
              <span className="badge badge-neutral flex items-center gap-1">
                <AlertTriangle size={12} />
                ランタイム状態を取得できません
              </span>
            ) : runtimeData ? (
              <>
                {/* claude CLI バッジ: 未検出時は復旧導線を付ける */}
                {runtimeData.claude.available ? (
                  <span className="badge badge-green">claude CLI 検出</span>
                ) : (
                  <span className="flex items-center gap-1">
                    <span className="badge badge-red">claude CLI 未検出</span>
                    {runtimeData.claude.binary ? (
                      <span className="text-xs text-muted">({runtimeData.claude.binary})</span>
                    ) : null}
                    <a
                      href="https://docs.anthropic.com/ja/docs/claude-code"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-ghost btn-sm"
                      title="インストール手順を確認する"
                    >
                      <ExternalLink size={12} />
                      インストール手順
                    </a>
                  </span>
                )}

                {/* wmux バッジ: 状態に応じた復旧導線 */}
                {(() => {
                  const info = wmuxInfo(runtimeData.wmux.state)
                  return (
                    <span className="flex items-center gap-1">
                      <span className={`badge ${info.badge}`}>{info.label}</span>
                      {runtimeData.wmux.state === 'awaiting-approval' ? (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => navigate('/sessions')}
                          title="承認インボックスを確認する"
                        >
                          承認する
                        </button>
                      ) : runtimeData.wmux.state !== 'connected' ? (
                        <span className="text-xs text-muted">wmux の起動・再接続が必要です</span>
                      ) : null}
                    </span>
                  )
                })()}

                <span className="badge badge-neutral">ドライバー: {runtimeData.driver}</span>
              </>
            ) : (
              <span className="badge badge-neutral">ランタイム情報を読み込み中…</span>
            )}
          </div>
        </div>

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
                <p>
                  チャットの <code>/analyze</code>・<code>/goal</code> を実行すると、wmux
                  上にエージェントのタブが生成され、ここにライブ表示されます。
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !loadError && sessions.length > 0 ? (
          /* レスポンシブ: sm 以下は 1 カラム、md 以上は 2 カラム */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            <div className="flex flex-col gap-4">
              {sessions.map((session) => {
                const isDone =
                  session.status === 'done' ||
                  session.status === 'completed' ||
                  session.status === 'failed'
                const isStopping = stoppingId === session.id
                return (
                  <div key={session.id} className="card">
                    <div className="card-header">
                      <div className="flex-1 min-w-0">
                        <div className="card-title">{session.name}</div>
                        {/* created_at を表示、session.id はコピー可能に縮小表示 */}
                        <div className="card-description flex items-center gap-2 flex-wrap">
                          <span>{formatDateTime(session.created_at)}</span>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm font-mono text-xs max-w-28 truncate"
                            onClick={() => copyToClipboard(session.id)}
                            title={`ID: ${session.id}（クリックでコピー）`}
                          >
                            <ClipboardCopy size={11} />
                            <span className="truncate">{session.id}</span>
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`badge ${statusBadge(session.status)}`}>
                          {statusLabel(session.status)}
                        </span>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => handleStopClick(session)}
                          disabled={isDone || isStopping}
                          aria-label={`${session.name} を停止`}
                        >
                          {isStopping ? (
                            <RefreshCw size={13} className="animate-spin" />
                          ) : (
                            <Square size={13} />
                          )}
                          {isStopping ? '停止中…' : '停止'}
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
                              {session.surfaces.map((surface) => {
                                const isSelected =
                                  selected?.sessionId === session.id &&
                                  selected?.agentId === surface.agent_id
                                const exitCode = surface.exit_code
                                const exitCodeStr =
                                  exitCode === null || exitCode === undefined ? '—' : String(exitCode)
                                const exitCodeIsError = exitCode !== null && exitCode !== undefined && exitCode !== 0
                                return (
                                  <tr key={surface.id} className={isSelected ? 'bg-blue-50/50' : undefined}>
                                    <td>
                                      <div className="font-semibold">{surface.title}</div>
                                      <div className="text-xs text-muted">{surface.agent_id}</div>
                                    </td>
                                    <td>
                                      <span className={`badge ${statusBadge(surface.status)}`}>
                                        {statusLabel(surface.status)}
                                      </span>
                                    </td>
                                    <td className={`mono text-sm ${exitCodeIsError ? 'text-red-600 font-bold' : ''}`}>
                                      {exitCodeStr}
                                    </td>
                                    <td>
                                      <button
                                        type="button"
                                        className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-ghost'}`}
                                        onClick={() =>
                                          void openLog(session.id, surface.agent_id, surface.title)
                                        }
                                      >
                                        <FileText size={13} />
                                        表示
                                      </button>
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* ログパネル: WS イベントで自動追従するライブ監視 */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">エージェントログ</div>
                  <div className="card-description">
                    各エージェントの claude 出力（stream-json）をライブで確認できます。
                  </div>
                </div>
                {selected ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => selected && void fetchLog(selected.sessionId, selected.agentId)}
                      disabled={logLoading}
                      aria-label="ログを再読込"
                    >
                      <RefreshCw size={13} className={logLoading ? 'animate-spin' : undefined} />
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setSelected(null); setLogText(''); setLogError(null) }}>
                      閉じる
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="card-body">
                {selected ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold">{selected.title}</div>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => copyToClipboard(logText)}
                        disabled={!logText}
                        title="ログをコピー"
                      >
                        <ClipboardCopy size={13} />
                        コピー
                      </button>
                    </div>
                    {logLoading ? (
                      <div className="flex items-center gap-3">
                        <div className="spinner" />
                        <div className="text-muted">ログを取得中…</div>
                      </div>
                    ) : logError ? (
                      <div className="empty-state">
                        <AlertTriangle className="empty-state-icon" size={20} />
                        <h3>ログの取得に失敗しました</h3>
                        <p>{logError}</p>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => selected && void fetchLog(selected.sessionId, selected.agentId)}
                        >
                          再試行
                        </button>
                      </div>
                    ) : logText ? (
                      <div className="relative">
                        <pre className="progress-log">{logText}</pre>
                        <div ref={logEndRef} />
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm absolute bottom-2 right-2"
                          onClick={() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' })}
                          title="末尾へジャンプ"
                        >
                          末尾
                        </button>
                      </div>
                    ) : (
                      <div className="empty-state">
                        <Terminal className="empty-state-icon" size={20} />
                        <h3>まだ出力がありません</h3>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="empty-state">
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
