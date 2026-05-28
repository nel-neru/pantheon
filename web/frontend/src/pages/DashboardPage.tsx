import { useCallback, useEffect, useState } from 'react'
import { Activity, Power, RefreshCw, Terminal } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { healthClass } from '@/lib/utils'

type PlatformStatus = {
  group_health_score: number
  balance_score: number
  total_organizations: number
  active_organizations: number
  weakest_organization: string | null
  strongest_organization: string | null
  platform_home: string
  initialized: boolean
  has_llm: boolean
}

type SettingsData = {
  llm_provider: string
  llm_model: string
  settings_file: string
  has_llm: boolean
}

type Organization = {
  id: string
  name: string
  purpose: string
  health_score: number
  autonomy_score: number
  total_agents: number
  pending_proposals: number
  target_repo_path: string
  status: string
  last_active: string | null
}

type DaemonStatus = {
  running: boolean
  pid: number | null
  log_path: string | null
}

type TaskStats = {
  total: number
  pending: number
  running: number
  done: number
  failed: number
}

type TaskItem = {
  id: string
  org_name: string
  description: string
  status: string
}

type TaskQueueResponse = {
  tasks: TaskItem[]
  stats: TaskStats
}

export function DashboardPage() {
  const [platform, setPlatform] = useState<PlatformStatus | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [daemon, setDaemon] = useState<DaemonStatus | null>(null)
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null)
  const [recentTasks, setRecentTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [daemonAction, setDaemonAction] = useState<'start' | 'stop' | null>(null)
  const [settingsError, setSettingsError] = useState(false)

  const loadData = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }

    try {
      const results = await Promise.allSettled([
        api<PlatformStatus>('GET', '/api/platform/status'),
        api<SettingsData>('GET', '/api/settings'),
        api<Organization[]>('GET', '/api/organizations'),
        api<DaemonStatus>('GET', '/api/daemon/status'),
        api<TaskQueueResponse>('GET', '/api/tasks'),
      ])

      const [platformResult, settingsResult, orgsResult, daemonResult, taskQueueResult] = results

      if (platformResult.status === 'fulfilled') {
        setPlatform(platformResult.value)
      }

      if (settingsResult.status === 'fulfilled') {
        setSettings(settingsResult.value)
        setSettingsError(false)
      } else {
        setSettings(null)
        setSettingsError(true)
      }

      if (orgsResult.status === 'fulfilled') {
        setOrganizations(orgsResult.value)
      }

      if (daemonResult.status === 'fulfilled') {
        setDaemon(daemonResult.value)
      }

      if (taskQueueResult.status === 'fulfilled') {
        setTaskStats(taskQueueResult.value.stats)
        setRecentTasks(taskQueueResult.value.tasks)
      } else {
        setTaskStats(null)
        setRecentTasks([])
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
    const interval = window.setInterval(() => {
      void loadData(true)
    }, 30000)

    return () => window.clearInterval(interval)
  }, [loadData])

  const refreshTasks = async () => {
    try {
      const result = await api<TaskQueueResponse>('GET', '/api/tasks')
      setTaskStats(result.stats)
      setRecentTasks(result.tasks)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'タスクキューの更新に失敗しました。')
    }
  }

  const handleInitialize = async () => {
    setInitializing(true)
    try {
      const result = await api<{ message: string }>('POST', '/api/init')
      toast.success(result.message || 'プラットフォームを初期化しました。')
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'プラットフォームの初期化に失敗しました。')
    } finally {
      setInitializing(false)
    }
  }

  const handleDaemon = async (action: 'start' | 'stop') => {
    setDaemonAction(action)
    try {
      const result = await api<{ message: string }>('POST', `/api/daemon/${action}`)
      toast.success(result.message || 'デーモンの操作が完了しました。')
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'デーモンの操作に失敗しました。')
    } finally {
      setDaemonAction(null)
    }
  }

  const llmReady = settings?.has_llm ?? platform?.has_llm ?? false
  const systemInfoBadgeClass = settingsError ? 'badge-yellow' : llmReady ? 'badge-green' : 'badge-red'
  const systemInfoBadgeLabel = settingsError ? '要再起動' : llmReady ? 'LLM 接続済み' : 'LLM 未設定'
  const taskStatusClass = (status: string) => {
    if (status === 'running') return 'badge-blue'
    if (status === 'done') return 'badge-green'
    if (status === 'failed') return 'badge-red'
    return 'badge-neutral'
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">プラットフォーム</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleInitialize}
            disabled={initializing}
          >
            <Activity size={14} />
            {initializing ? '初期化中' : '初期化'}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void loadData(true)}
            disabled={refreshing}
          >
            <RefreshCw size={14} />
            {refreshing ? '更新中' : '更新'}
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">プラットフォーム状態を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {platform ? (
          <div className="grid-2">
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">プラットフォーム状態</div>
                  <div className="card-description">現在の RepoCorp AI 環境とヘルスの概要です。</div>
                </div>
                <div className={`badge ${platform.has_llm ? 'badge-green' : 'badge-red'}`}>
                  {platform.has_llm ? 'LLM 準備完了' : 'LLM 未設定'}
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="metrics-grid">
                  <div className="metric-card">
                    <div className="metric-label">ヘルス</div>
                    <div className="metric-value mono">{platform.group_health_score.toFixed(1)}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">組織数</div>
                    <div className="metric-value">{platform.total_organizations}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">アクティブ</div>
                    <div className="metric-value">{platform.active_organizations}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">バランス</div>
                    <div className="metric-value mono">{platform.balance_score.toFixed(0)}</div>
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted mb-2">ホームパス</div>
                  <div className="mono text-sm text-fg2">{platform.platform_home}</div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">ヘルススコア</div>
                  <div className="card-description">組織全体の統合ヘルススコアです。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="metric-value mono">{platform.group_health_score.toFixed(1)}</div>
                <div className="health-track">
                  <div
                    className={`health-fill ${healthClass(platform.group_health_score)}`}
                    style={{ width: `${platform.group_health_score}%` }}
                  />
                </div>
                <div className="text-sm text-muted">{platform.total_organizations} 件の組織を監視中です。</div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">タスクキュー</div>
              <div className="card-description">実行中・待機中のタスク</div>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refreshTasks()}>
              更新
            </button>
          </div>
          <div className="card-body">
            {taskStats ? (
              <div className="metrics-grid">
                <div className="metric-card">
                  <div className="metric-label">待機中</div>
                  <div className="metric-value">{taskStats.pending}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">実行中</div>
                  <div className="metric-value">{taskStats.running}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">完了</div>
                  <div className="metric-value">{taskStats.done}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">失敗</div>
                  <div className="metric-value">{taskStats.failed}</div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted">タスク統計を読み込めませんでした。</div>
            )}
            {recentTasks.length > 0 ? (
              <div className="task-list mt-3">
                {recentTasks.slice(0, 5).map((task) => (
                  <div key={task.id} className="task-item">
                    <span className={`badge ${taskStatusClass(task.status)}`}>{task.status}</span>
                    <span className="text-sm truncate flex-1" title={task.description}>{task.description}</span>
                    <span className="text-xs text-muted">{task.org_name}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted mt-3">最近のタスクはまだありません。</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">組織一覧</div>
              <div className="card-description">組織別のヘルスと提案数の一覧です。</div>
            </div>
          </div>
          <div className="card-body">
            {organizations.length === 0 ? (
              <div className="empty-state">
                <Activity className="empty-state-icon" size={28} />
                <h3>組織がありません</h3>
                <p>組織を作成してリポジトリ分析を始めてください。</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>名前</th>
                      <th>ヘルス</th>
                      <th>提案数</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {organizations.map((org) => (
                      <tr key={org.name}>
                        <td>
                          <div className="font-semibold">{org.name}</div>
                          <div className="text-xs text-muted">{org.purpose}</div>
                        </td>
                        <td>
                          <div className="flex flex-col gap-2">
                            <div className="mono text-sm">{org.health_score}</div>
                            <div className="health-track">
                              <div
                                className={`health-fill ${healthClass(org.health_score)}`}
                                style={{ width: `${org.health_score}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td>{org.pending_proposals}</td>
                        <td>
                          <div className="flex gap-2">
                            <Link
                              className="btn btn-secondary btn-sm"
                              to={`/proposals?org=${encodeURIComponent(org.name)}`}
                            >
                              提案を開く
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">デーモン状態</div>
              <div className="card-description">バックグラウンドオーケストレーションプロセスの管理です。</div>
            </div>
            <div className={`badge ${daemon?.running ? 'badge-green' : 'badge-neutral'}`}>
              {daemon?.running ? '起動中' : '停止'}
            </div>
          </div>
          <div className="card-body flex flex-col gap-4">
            <div className="grid-2">
              <div className="metric-card">
                <div className="metric-label">PID</div>
                <div className="metric-value">{daemon?.pid ?? '—'}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">ログパス</div>
                <div className="metric-desc mono text-fg2">{daemon?.log_path ?? '未設定'}</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void handleDaemon('start')}
                disabled={daemonAction !== null || Boolean(daemon?.running)}
              >
                <Power size={14} />
                {daemonAction === 'start' ? '起動中' : '起動'}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => void handleDaemon('stop')}
                disabled={daemonAction !== null || !daemon?.running}
              >
                <Terminal size={14} />
                {daemonAction === 'stop' ? '停止中' : '停止'}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">システム情報</div>
              <div className="card-description">LLM 接続と設定ファイルの状態です。</div>
            </div>
            <div className={`badge ${systemInfoBadgeClass}`}>{systemInfoBadgeLabel}</div>
          </div>
          <div className="card-body flex flex-col gap-3">
            {settingsError ? (
              <div className="settings-status-bar warn">
                <span className="badge badge-yellow">要再起動</span>
                <span className="text-sm text-muted">
                  システム情報を取得できませんでした。サーバーを再起動してください: <code>python main.py serve</code>
                </span>
              </div>
            ) : (
              <>
                <div className="data-kv-list">
                  <div className="data-kv-row">
                    <span className="data-kv-key">LLM 接続</span>
                    <span className={`badge ${llmReady ? 'badge-green' : 'badge-red'}`}>
                      {llmReady ? '利用可能' : '未設定'}
                    </span>
                  </div>
                  <div className="data-kv-row">
                    <span className="data-kv-key">プロバイダー</span>
                    <span className="data-kv-val">{settings?.llm_provider || '—'}</span>
                  </div>
                  <div className="data-kv-row">
                    <span className="data-kv-key">モデル</span>
                    <span className="data-kv-val mono">{settings?.llm_model || '—'}</span>
                  </div>
                  <div className="data-kv-row">
                    <span className="data-kv-key">設定ファイル</span>
                    <span className="data-kv-val mono">{settings?.settings_file || '—'}</span>
                  </div>
                  {platform ? (
                    <div className="data-kv-row">
                      <span className="data-kv-key">初期化状態</span>
                      <span className={`badge ${platform.initialized ? 'badge-green' : 'badge-neutral'}`}>
                        {platform.initialized ? '完了' : '未完了'}
                      </span>
                    </div>
                  ) : null}
                </div>
                {!llmReady ? (
                  <div className="text-xs text-muted">
                    設定画面で API キーを保存すると、ここに接続状態が反映されます。
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
