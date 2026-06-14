import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, Clock3, Copy, Power, Square } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { OrchestraView } from '@/components/OrchestraView'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { ScoreBar } from '@/components/ScoreBar'
import { api } from '@/lib/api'
import { statusLabel, statusBadge } from '@/lib/labels'
import { formatDateTime, formatScore } from '@/lib/utils'

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

function taskProgress(task: TaskItem): number | null {
  const payloadProgress = task.payload?.progress
  if (typeof payloadProgress === 'number') {
    return Math.max(0, Math.min(100, payloadProgress))
  }
  if (task.status === 'done' || task.status === 'failed') return 100
  return null
}

function copyToClipboard(text: string, label: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success(`${label}をコピーしました`),
    () => toast.error('コピーに失敗しました'),
  )
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
  const [loadError, setLoadError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [daemonAction, setDaemonAction] = useState<'start' | 'stop' | null>(null)
  const [settingsError, setSettingsError] = useState(false)

  // Confirm dialog state
  const [confirmInit, setConfirmInit] = useState(false)
  const [confirmDaemonStop, setConfirmDaemonStop] = useState(false)

  const loadData = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
      setLoadError(null)
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
      } else if (!silent) {
        setLoadError('プラットフォーム状態の読み込みに失敗しました。')
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

  const handleInitialize = async () => {
    setInitializing(true)
    try {
      const result = await api<{ message: string }>('POST', '/api/init')
      toast.success(result.message || 'プラットフォームを初期化しました。')
      await loadData()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'プラットフォームの初期化に失敗しました。')
      throw error
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
      throw error
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
  // Honest: this is only from the 40-item window, not lifetime totals
  const approvalRate =
    approvedCount + rejectedCount > 0
      ? `${((approvedCount / (approvedCount + rejectedCount)) * 100).toFixed(0)}%`
      : '—'

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

  const velocityHasData = velocityData.some((d) => d.created > 0 || d.approved > 0)

  const filteredHistory = useMemo(
    () =>
      executionHistory.filter((item) => {
        const query = historySearch.trim().toLowerCase()
        if (!query) return true
        return [item.title, item.details, item.org_name, item.operation].some((value) =>
          (value ?? '').toLowerCase().includes(query),
        )
      }),
    [executionHistory, historySearch],
  )

  // Summary orgs: worst 3 by health
  const summaryOrgs = useMemo(
    () => [...organizations].sort((a, b) => a.health_score - b.health_score).slice(0, 3),
    [organizations],
  )

  return (
    <>
      <PageHeader
        title="プラットフォーム"
        actions={
          <RefreshButton
            onClick={() => void loadData(true)}
            busy={refreshing}
          />
        }
      />

      {/* Confirm: platform re-initialize */}
      <ConfirmDialog
        open={confirmInit}
        onOpenChange={setConfirmInit}
        title={platform?.initialized ? 'プラットフォームを再初期化しますか？' : 'プラットフォームを初期化しますか？'}
        description={
          platform?.initialized
            ? '既存の組織設定・メタデータを上書きします。この操作は取り消せません。'
            : 'Pantheon プラットフォームのセットアップを開始します。'
        }
        confirmLabel={initializing ? '初期化中…' : platform?.initialized ? '再初期化する' : '初期化する'}
        onConfirm={handleInitialize}
      />

      {/* Confirm: daemon stop */}
      <ConfirmDialog
        open={confirmDaemonStop}
        onOpenChange={setConfirmDaemonStop}
        title="稼働中のオーケストレーションを停止しますか？"
        description="バックグラウンドで実行中の改善・コンテンツ自動化が中断されます。"
        confirmLabel={daemonAction === 'stop' ? '停止中…' : '停止する'}
        onConfirm={() => handleDaemon('stop')}
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={loadError}
          onRetry={() => void loadData()}
          loadingText="プラットフォーム状態を読み込み中…"
        >
          <>
            {/* ── 統合: プラットフォーム状態＋ヘルスゲージ ── */}
            {platform ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">プラットフォーム状態</div>
                    <div className="card-description">現在の Pantheon 環境とヘルスの概要です。</div>
                  </div>
                  <div className={`badge ${llmReady ? 'badge-green' : 'badge-red'}`}>
                    {llmReady ? 'LLM 準備完了' : 'LLM 未設定'}
                  </div>
                </div>
                <div className="card-body flex flex-col gap-4">
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-label">組織数</div>
                      <div className="metric-value">{organizations.length}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">アクティブ</div>
                      <div className="metric-value">{platform.active_organizations}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">総エージェント数</div>
                      <div className="metric-value">{agentCount}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-label">バランス</div>
                      <div className="metric-value mono" title="組織間の能力バランス指数 (0–100)">{formatScore(platform.balance_score, 0)}</div>
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-muted mb-2">プラットフォームヘルス</div>
                    <ScoreBar score={platform.group_health_score} label="プラットフォームヘルス" />
                  </div>
                  {platform.weakest_organization ? (
                    <div className="text-xs text-muted">
                      最弱組織: <span className="text-fg2">{platform.weakest_organization}</span>
                    </div>
                  ) : null}
                  <div>
                    <div className="text-sm text-muted mb-1">ホームパス</div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm font-mono text-xs text-fg2 truncate max-w-full"
                      title={`${platform.platform_home} (クリックでコピー)`}
                      onClick={() => copyToClipboard(platform.platform_home, 'パス')}
                    >
                      <Copy size={12} aria-hidden="true" />
                      {platform.platform_home}
                    </button>
                  </div>
                  {!platform.initialized ? (
                    <div className="flex items-center gap-3">
                      <span className="badge badge-yellow">未初期化</span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setConfirmInit(true)}
                        disabled={initializing}
                      >
                        <Activity size={14} />
                        初回セットアップ
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            <OrchestraView />

            {/* ── 主要メトリクス（直近40件ウィンドウ正直化済み） ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">主要メトリクス</div>
                  <div className="card-description">提案・承認率は直近40件の実行履歴ウィンドウ内の集計です。</div>
                </div>
              </div>
              <div className="card-body">
                <div className="metrics-grid">
                  <div className="metric-card">
                    <div className="metric-label">承認数（直近40件中）</div>
                    <div className="metric-value">{approvedCount}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">却下数（直近40件中）</div>
                    <div className="metric-value">{rejectedCount}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">承認率（直近40件中）</div>
                    <div className="metric-value mono">{approvalRate}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">保留提案</div>
                    <div className="metric-value">
                      {organizations.reduce((sum, org) => sum + org.pending_proposals, 0)}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ── 改善速度チャート (recharts) ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">改善速度</div>
                  <div className="card-description">直近 6 日間の提案生成数 / 承認数（直近40件履歴内）。</div>
                </div>
              </div>
              <div className="card-body">
                {velocityHasData ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={velocityData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip
                        labelFormatter={(label) => String(label)}
                        formatter={(value, name) => [value, name === 'created' ? '作成' : '承認']}
                        contentStyle={{ fontSize: 12 }}
                      />
                      <Bar dataKey="created" name="作成" fill="var(--color-accent)" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="approved" name="承認" fill="var(--color-green)" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    title="直近6日間のデータがありません"
                    hint="改善提案が実行されると速度チャートが表示されます。"
                  />
                )}
              </div>
            </div>

            {/* ── 統合タスクカード: stats + アクティブタスク ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">タスク</div>
                  <div className="card-description">実行中・待機中のタスクを 10 秒ごとに自動更新します。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
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
                {activeTasks.length > 0 ? (
                  <div className="flex flex-col gap-3">
                    <div className="text-sm text-muted">アクティブタスク</div>
                    {activeTasks.map((task) => (
                      <div key={task.id} className="rounded-xl border border-white/10 p-3 flex flex-col gap-2">
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <div>
                            <div className="font-semibold">{task.description}</div>
                            <div className="text-xs text-muted">{task.org_name}</div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`badge ${statusBadge(task.status)}`}>
                              {statusLabel(task.status)}
                            </span>
                            <span className="text-xs text-muted inline-flex items-center gap-1">
                              <Clock3 size={12} />
                              {formatElapsed(task)}
                            </span>
                          </div>
                        </div>
                        {taskProgress(task) !== null && (
                          <ScoreBar
                            score={taskProgress(task) ?? 0}
                            label={`進捗 ${taskProgress(task) ?? 0}%`}
                            showValue
                          />
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-muted">現在監視対象の実行はありません。</div>
                )}
                {recentTasks.length > 0 && activeTasks.length === 0 ? (
                  <div className="task-list">
                    {recentTasks.slice(0, 5).map((task) => (
                      <div key={task.id} className="task-item">
                        <span className={`badge ${statusBadge(task.status)}`}>{statusLabel(task.status)}</span>
                        <span className="text-sm truncate flex-1" title={task.description}>
                          {task.description}
                        </span>
                        <span className="text-xs text-muted">{formatDateTime(task.created_at)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            {/* ── 実行履歴 / 監査ログ ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">実行履歴 / 監査ログ</div>
                  <div className="card-description">
                    直近40件のログを絞り込み検索できます（全文検索はサーバー未対応）。
                  </div>
                </div>
                <input
                  className="input history-search-input"
                  value={historySearch}
                  onChange={(event) => setHistorySearch(event.target.value)}
                  placeholder="組織名・操作名・詳細で絞り込み"
                  aria-label="実行履歴を絞り込み"
                />
              </div>
              <div className="card-body">
                {filteredHistory.length === 0 ? (
                  <div className="text-sm text-muted">
                    {historySearch ? `「${historySearch}」に一致する履歴がありません。` : '実行履歴がまだありません。'}
                  </div>
                ) : (
                  <>
                    <div className="history-list">
                      {filteredHistory.map((item) => (
                        <div key={item.id} className="history-item">
                          <div className="history-item-head">
                            <span className={`badge ${statusBadge(item.status)}`}>
                              {statusLabel(item.status)}
                            </span>
                            <span
                              className="text-xs text-muted"
                              title={item.timestamp}
                            >
                              {formatDateTime(item.timestamp)}
                            </span>
                            {/* 承認インボックスへの導線 */}
                            {(item.operation === 'proposal_created' ||
                              item.operation === 'handoff_created') ? (
                              <Link
                                to="/inbox"
                                className="text-xs text-blue-400 hover:underline ml-auto"
                              >
                                承認インボックスで開く →
                              </Link>
                            ) : null}
                          </div>
                          <div className="history-item-title">{item.title}</div>
                          <div className="history-item-details">{item.details || item.operation}</div>
                          {item.org_name ? (
                            <div className="text-xs text-muted">{item.org_name}</div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                    {filteredHistory.length > 0 ? (
                      <div className="text-xs text-muted mt-2">
                        {historySearch
                          ? `${filteredHistory.length} 件一致（直近40件中）`
                          : `直近 ${filteredHistory.length} 件を表示`}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            {/* ── 組織サマリ（ヘルス下位3件）→ 全件は /orgs ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">組織サマリ</div>
                  <div className="card-description">
                    ヘルスが低い組織のトップ3です。全件一覧は{' '}
                    <Link to="/orgs" className="text-blue-400 hover:underline">
                      組織ページ
                    </Link>{' '}
                    で確認できます。
                  </div>
                </div>
                <Link to="/orgs" className="btn btn-ghost btn-sm">
                  全件を見る →
                </Link>
              </div>
              <div className="card-body">
                {organizations.length === 0 ? (
                  <EmptyState
                    icon={Activity}
                    title="組織がありません"
                    hint="組織を作成してリポジトリ分析を始めてください。"
                    action={
                      <Link to="/orgs" className="btn btn-secondary btn-sm">
                        組織を作成・管理する →
                      </Link>
                    }
                  />
                ) : (
                  <div className="flex flex-col gap-3">
                    {summaryOrgs.map((org) => (
                      <div
                        key={org.name}
                        className="flex items-center gap-3 rounded-xl border border-white/10 p-3"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold truncate">{org.name}</div>
                          <div className="text-xs text-muted truncate">{org.purpose}</div>
                        </div>
                        <div className="flex flex-col gap-1 w-32 shrink-0">
                          <ScoreBar score={org.health_score} label={`${org.name} ヘルス`} />
                        </div>
                        <div className="text-xs text-muted shrink-0">提案 {org.pending_proposals}</div>
                        <Link
                          to={`/proposals?org=${encodeURIComponent(org.name)}`}
                          className="btn btn-secondary btn-sm shrink-0"
                        >
                          提案を開く
                        </Link>
                      </div>
                    ))}
                    {organizations.length > 3 ? (
                      <div className="text-xs text-muted">
                        他 {organizations.length - 3} 件 →{' '}
                        <Link to="/orgs" className="text-blue-400 hover:underline">
                          組織ページ
                        </Link>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </div>

            {/* ── デーモン状態 ── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">デーモン状態</div>
                  <div className="card-description">
                    バックグラウンドオーケストレーションプロセスの管理です。
                    複数デーモンの詳細管理は専用ページで確認してください。
                  </div>
                </div>
                <div className={`badge ${daemon?.running ? 'badge-green' : 'badge-neutral'}`}>
                  {daemon?.running ? '起動中' : '停止'}
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                {daemon?.running && daemon.pid !== null ? (
                  <div className="text-xs text-muted">PID: {daemon.pid}</div>
                ) : null}
                {daemon?.log_path ? (
                  <div>
                    <div className="text-sm text-muted mb-1">ログパス</div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm font-mono text-xs text-fg2 truncate max-w-full"
                      title={`${daemon.log_path} (クリックでコピー)`}
                      onClick={() => copyToClipboard(daemon.log_path ?? '', 'ログパス')}
                    >
                      <Copy size={12} aria-hidden="true" />
                      {daemon.log_path}
                    </button>
                  </div>
                ) : null}
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
                    onClick={() => setConfirmDaemonStop(true)}
                    disabled={daemonAction !== null || !daemon?.running}
                  >
                    <Square size={14} />
                    停止
                  </button>
                </div>
              </div>
            </div>

            {/* ── システム情報 ── */}
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
                      システム情報を取得できませんでした。サーバーを再起動してください:{' '}
                      <code>pantheon serve</code>
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
                        LLM が未設定です。<code>claude</code> CLI でログインするか、
                        <Link to="/settings" className="text-blue-400 hover:underline ml-1">
                          設定ページ
                        </Link>
                        で認証状態を確認してください。
                      </div>
                    ) : null}
                    {platform?.initialized ? null : (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm self-start"
                        onClick={() => setConfirmInit(true)}
                        disabled={initializing}
                      >
                        <Activity size={14} />
                        {platform?.initialized ? '再初期化' : '初期化'}
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </>
        </AsyncBoundary>
      </div>
    </>
  )
}
