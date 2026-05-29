import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, Clock3, Power, RefreshCw, Terminal } from 'lucide-react'
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
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  payload?: {
    progress?: number
    [key: string]: unknown
  }
}

type TaskQueueResponse = {
  tasks: TaskItem[]
  stats: TaskStats
}

type ExecutionHistoryItem = {
  id: string
  timestamp: string
  operation: string
  status: string
  title: string
  details: string
  org_name?: string | null
  entity_type?: string | null
}

function taskStatusClass(status: string) {
  if (status === 'running') return 'badge-blue'
  if (status === 'done') return 'badge-green'
  if (status === 'failed') return 'badge-red'
  if (status === 'pending') return 'badge-yellow'
  return 'badge-neutral'
}

function formatElapsed(task: TaskItem) {
  const start = task.started_at || task.created_at
  if (!start) return '開始待ち'
  const startMs = Date.parse(start)
  if (Number.isNaN(startMs)) return '計測不可'
  const endMs = task.completed_at ? Date.parse(task.completed_at) : Date.now()
  const seconds = Math.max(0, Math.floor((endMs - startMs) / 1000))
  const minutes = Math.floor(seconds / 60)
  if (minutes > 0) return `${minutes}分 ${seconds % 60}秒`
  return `${seconds}秒`
}

function taskProgress(task: TaskItem) {
  const payloadProgress = task.payload?.progress
  if (typeof payloadProgress === 'number') {
    return Math.max(0, Math.min(100, payloadProgress))
  }
  if (task.status === 'done') return 100
  if (task.status === 'failed') return 100
  if (task.status === 'running') return 65
  if (task.status === 'pending') return 20
  return 0
}

export function DashboardPage() {
  const [platform, setPlatform] = useState<PlatformStatus | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [daemon, setDaemon] = useState<DaemonStatus | null>(null)
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null)
  const [recentTasks, setRecentTasks] = useState<TaskItem[]>([])
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistoryItem[]>([])
  const [historySearch, setHistorySearch] = useState('')
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
        api<ExecutionHistoryItem[]>('GET', '/api/execution-history?limit=40'),
      ])

      const [platformResult, settingsResult, orgsResult, daemonResult, taskQueueResult, historyResult] = results

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

      if (historyResult.status === 'fulfilled') {
        setExecutionHistory(historyResult.value)
      } else {
        setExecutionHistory([])
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
    }, 10000)

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
  const activeTasks = useMemo(
    () => recentTasks.filter((task) => task.status === 'running' || task.status === 'pending').slice(0, 6),
    [recentTasks],
  )
  const approvedCount = useMemo(
    () => executionHistory.filter((item) => item.operation === 'proposal_approved').length,
    [executionHistory],
  )
  const rejectedCount = useMemo(
    () => executionHistory.filter((item) => item.operation === 'proposal_rejected').length,
    [executionHistory],
  )
  const agentCount = useMemo(
    () => organizations.reduce((sum, org) => sum + org.total_agents, 0),
    [organizations],
  )
  const totalProposals = useMemo(
    () => organizations.reduce((sum, org) => sum + org.pending_proposals, 0) + approvedCount + rejectedCount,
    [approvedCount, organizations, rejectedCount],
  )
  const approvalRate = approvedCount + rejectedCount > 0 ? (approvedCount / (approvedCount + rejectedCount)) * 100 : 0
  const velocityData = useMemo(() => {
    const labels = Array.from({ length: 6 }, (_, index) => {
      const date = new Date()
      date.setDate(date.getDate() - (5 - index))
      const key = date.toISOString().slice(0, 10)
      return {
        key,
        label: `${date.getMonth() + 1}/${date.getDate()}`,
        created: 0,
        approved: 0,
      }
    })
    const byKey = new Map(labels.map((item) => [item.key, item]))

    executionHistory.forEach((item) => {
      const key = item.timestamp.slice(0, 10)
      const current = byKey.get(key)
      if (!current) return
      if (item.operation === 'proposal_created') current.created += 1
      if (item.operation === 'proposal_approved') current.approved += 1
    })

    return labels
  }, [executionHistory])
  const velocityMax = Math.max(1, ...velocityData.flatMap((item) => [item.created, item.approved]))
  const filteredHistory = useMemo(
    () => executionHistory.filter((item) => {
      const query = historySearch.trim().toLowerCase()
      if (!query) return true
      return [item.title, item.details, item.org_name, item.operation].some((value) =>
        (value ?? '').toLowerCase().includes(query),
      )
    }),
    [executionHistory, historySearch],
  )

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
              <div className="card-title">主要メトリクス</div>
              <div className="card-description">組織・提案・承認率・エージェント数のサマリーです。</div>
            </div>
          </div>
          <div className="card-body">
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-label">総組織数</div>
                <div className="metric-value">{organizations.length}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">総提案数</div>
                <div className="metric-value">{totalProposals}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">承認率</div>
                <div className="metric-value mono">{approvalRate.toFixed(0)}%</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">総エージェント数</div>
                <div className="metric-value">{agentCount}</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">改善速度</div>
              <div className="card-description">直近 6 日間の提案生成数 / 承認数です。</div>
            </div>
            <div className="chart-legend">
              <span className="chart-legend-item"><span className="chart-swatch created" />作成</span>
              <span className="chart-legend-item"><span className="chart-swatch approved" />承認</span>
            </div>
          </div>
          <div className="card-body">
            <div className="velocity-chart">
              <svg viewBox={`0 0 ${velocityData.length * 72} 190`} className="velocity-chart-svg" role="img" aria-label="改善速度チャート">
                {velocityData.map((item, index) => {
                  const baseX = index * 72 + 18
                  const createdHeight = (item.created / velocityMax) * 96
                  const approvedHeight = (item.approved / velocityMax) * 96
                  return (
                    <g key={item.key}>
                      <rect x={baseX} y={126 - createdHeight} width="18" height={createdHeight || 2} rx="4" className="chart-bar created" />
                      <rect x={baseX + 24} y={126 - approvedHeight} width="18" height={approvedHeight || 2} rx="4" className="chart-bar approved" />
                      <text x={baseX + 21} y="156" textAnchor="middle" className="chart-label">{item.label}</text>
                      <text x={baseX + 9} y={144 - createdHeight} textAnchor="middle" className="chart-value">{item.created}</text>
                      <text x={baseX + 33} y={144 - approvedHeight} textAnchor="middle" className="chart-value">{item.approved}</text>
                    </g>
                  )
                })}
              </svg>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">実行モニター</div>
              <div className="card-description">現在の running / pending タスクを 10 秒ごとに更新します。</div>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refreshTasks()}>
              更新
            </button>
          </div>
          <div className="card-body">
            {activeTasks.length === 0 ? (
              <div className="text-sm text-muted">現在監視対象の実行はありません。</div>
            ) : (
              <div className="flex flex-col gap-3">
                {activeTasks.map((task) => (
                  <div key={task.id} className="rounded-xl border border-white/10 p-3 flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div>
                        <div className="font-semibold">{task.description}</div>
                        <div className="text-xs text-muted">{task.org_name}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`badge ${taskStatusClass(task.status)}`}>{task.status}</span>
                        <span className="text-xs text-muted inline-flex items-center gap-1">
                          <Clock3 size={12} />
                          {formatElapsed(task)}
                        </span>
                      </div>
                    </div>
                    <div className="health-track">
                      <div
                        className={`health-fill ${task.status === 'pending' ? 'warning' : 'good'}`}
                        style={{ width: `${taskProgress(task)}%` }}
                      />
                    </div>
                    <div className="text-xs text-muted">進捗 {taskProgress(task)}%</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

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
              <div className="card-title">実行履歴 / 監査ログ</div>
              <div className="card-description">最近の操作と結果を検索できます。</div>
            </div>
            <input
              className="input history-search-input"
              value={historySearch}
              onChange={(event) => setHistorySearch(event.target.value)}
              placeholder="組織名・操作名・詳細で検索"
              aria-label="実行履歴を検索"
            />
          </div>
          <div className="card-body">
            {filteredHistory.length === 0 ? (
              <div className="text-sm text-muted">一致する履歴はまだありません。</div>
            ) : (
              <div className="history-list">
                {filteredHistory.slice(0, 8).map((item) => (
                  <div key={item.id} className="history-item">
                    <div className="history-item-head">
                      <span className={`badge ${item.status === 'error' ? 'badge-red' : item.status === 'pending' ? 'badge-yellow' : 'badge-green'}`}>
                        {item.status}
                      </span>
                      <span className="text-xs text-muted">{item.timestamp ? new Date(item.timestamp).toLocaleString('ja-JP') : '—'}</span>
                    </div>
                    <div className="history-item-title">{item.title}</div>
                    <div className="history-item-details">{item.details || item.operation}</div>
                    {item.org_name ? <div className="text-xs text-muted">{item.org_name}</div> : null}
                  </div>
                ))}
              </div>
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
