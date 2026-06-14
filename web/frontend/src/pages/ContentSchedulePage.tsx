import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CalendarClock,
  Loader2,
  Pause,
  PenSquare,
  Play,
  Plus,
  Trash2,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
import { statusLabel, statusBadge } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'

type ContentJob = {
  job_id: string
  org_name: string
  kind: string
  theme: string
  interval_seconds: number
  enabled: boolean
  last_run_at: string | null
  next_run_at: string | null
  last_status: string
  last_detail: string
  run_count: number
  publish_platform: string
  publish_mode: string
}

type DaemonStatus = {
  running: boolean
  pid: number | null
  rate_limited: boolean
  retry_at: string | null
  cycle_count: number
  interval_seconds: number | null
}

type CycleLog = {
  cycle: number
  completed_at?: string
  due_jobs?: number
  generated?: number
  interventions?: number
  rate_limited?: boolean
}

type OrgOption = { name: string; target_repo_path: string | null }

const KIND_LABELS: Record<string, string> = {
  content_brief: 'SNS 投稿',
  audience_signal: '需要シグナル',
  monetization_lead: '収益化リード',
  generic: '汎用下書き',
}

const KIND_DESCRIPTIONS: Record<string, string> = {
  content_brief: '短文の SNS 投稿ドラフトを定期生成します。',
  audience_signal: '需要・トレンドのシグナルレポートを作成します。',
  monetization_lead: '収益化につながるアイデアやリードを抽出します。',
  generic: '自由形式の下書きを生成します（テーマで内容を指定）。',
}

const PUBLISH_PLATFORMS: Record<string, string> = {
  note: 'note',
  x: 'X (Twitter)',
  wordpress: 'WordPress',
}

const INTERVAL_PRESETS = [
  { label: '1時間', value: 3600 },
  { label: '6時間', value: 21600 },
  { label: '1日', value: 86400 },
  { label: '1週間', value: 604800 },
]

const DAEMON_INTERVAL_PRESETS = [
  { label: '10分', value: 600 },
  { label: '30分', value: 1800 },
  { label: '1時間', value: 3600 },
]

function formatInterval(seconds: number) {
  if (seconds % 86400 === 0) return `${seconds / 86400}日`
  if (seconds % 3600 === 0) return `${seconds / 3600}時間`
  return `${Math.round(seconds / 60)}分`
}

// ---- 状態型 ----------------------------------------------------------------

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

// ---- ジョブカード子コンポーネント -------------------------------------------

type ContentJobCardProps = {
  job: ContentJob
  runningJobId: string | null
  togglingJobId: string | null
  onRunNow: (job: ContentJob) => void
  onToggle: (job: ContentJob) => void
  onDelete: (job: ContentJob) => void
  onOpenStudio: (job: ContentJob) => void
}

function ContentJobCard({
  job,
  runningJobId,
  togglingJobId,
  onRunNow,
  onToggle,
  onDelete,
  onOpenStudio,
}: ContentJobCardProps) {
  const isRunning = runningJobId === job.job_id
  const isToggling = togglingJobId === job.job_id
  const isFailed = job.last_status === 'error' || job.last_status === 'failed'

  return (
    <div className="rounded-xl border border-white/10 p-3 flex flex-col gap-2">
      {/* 上段: 名前 + バッジ */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="font-semibold">
            {job.org_name} · {KIND_LABELS[job.kind] ?? job.kind}
          </div>
          <div className="text-xs text-muted">{job.theme || '(テーマ未設定)'}</div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="badge badge-neutral">{formatInterval(job.interval_seconds)}ごと</span>
          <span className={`badge ${job.enabled ? 'badge-green' : 'badge-neutral'}`}>
            {job.enabled ? '有効' : '無効'}
          </span>
          {job.publish_platform ? (
            <span className="badge badge-green">
              {PUBLISH_PLATFORMS[job.publish_platform] ?? job.publish_platform}
            </span>
          ) : null}
        </div>
      </div>

      {/* 中段: 実行情報 */}
      <div className="text-xs text-muted">
        実行 {job.run_count} 回 ·{' '}
        最終: {formatDateTime(job.last_run_at)}{' '}
        {job.last_status ? (
          <span className={`badge badge-sm ${statusBadge(job.last_status)}`}>
            {statusLabel(job.last_status)}
          </span>
        ) : null}
        {' '}· 次回: {formatDateTime(job.next_run_at)}
      </div>

      {/* 失敗詳細 */}
      {isFailed && job.last_detail ? (
        <div className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">
          失敗原因: {job.last_detail}
        </div>
      ) : null}

      {/* 下段: 操作ボタン */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => onRunNow(job)}
          disabled={isRunning || runningJobId !== null}
        >
          {isRunning ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Zap size={13} />
          )}
          {isRunning ? '生成中…' : '今すぐ生成'}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => onToggle(job)}
          disabled={isToggling}
        >
          {isToggling ? (
            <Loader2 size={13} className="animate-spin" />
          ) : job.enabled ? (
            <Pause size={13} />
          ) : (
            <Play size={13} />
          )}
          {isToggling ? '更新中…' : job.enabled ? '無効化' : '有効化'}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm text-red-400"
          onClick={() => onDelete(job)}
        >
          <Trash2 size={13} /> 削除
        </button>
        {/* 生成済みコンテンツをスタジオで整えるための導線（テーマをシードとして渡す） */}
        {job.run_count > 0 ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm ml-auto"
            onClick={() => onOpenStudio(job)}
            title="スタジオを開いてコンテンツを確認・編集する"
          >
            <PenSquare size={13} />
            スタジオで整える
          </button>
        ) : null}
      </div>
    </div>
  )
}

// ---- メインコンポーネント ---------------------------------------------------

export function ContentSchedulePage() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<ContentJob[]>([])
  const [orgs, setOrgs] = useState<OrgOption[]>([])
  const [daemon, setDaemon] = useState<DaemonStatus | null>(null)
  const [logs, setLogs] = useState<CycleLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runningJobId, setRunningJobId] = useState<string | null>(null)
  const [togglingJobId, setTogglingJobId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const { events } = usePlatformUpdates()

  // フォーム
  const [orgName, setOrgName] = useState('')
  const [kind, setKind] = useState('content_brief')
  const [theme, setTheme] = useState('')
  const [interval, setIntervalSeconds] = useState(86400)
  const [publishPlatform, setPublishPlatform] = useState('')
  const [publishMode, setPublishMode] = useState('assisted')

  // ループ開始時の巡回間隔（可変・デフォルト10分）
  const [daemonInterval, setDaemonInterval] = useState(600)

  // WS デバウンス用
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [jobsRes, orgsRes, daemonRes, logsRes] = await Promise.allSettled([
        api<ContentJob[]>('GET', '/api/content-jobs'),
        api<OrgOption[]>('GET', '/api/organizations'),
        api<DaemonStatus>('GET', '/api/content-daemon/status'),
        api<CycleLog[]>('GET', '/api/content-daemon/logs?limit=10'),
      ])

      let hasError = false

      if (jobsRes.status === 'fulfilled') setJobs(jobsRes.value)
      else { hasError = true }

      if (orgsRes.status === 'fulfilled') setOrgs(orgsRes.value)

      if (daemonRes.status === 'fulfilled') setDaemon(daemonRes.value)
      else { hasError = true }

      if (logsRes.status === 'fulfilled') setLogs(logsRes.value)

      if (hasError) {
        const msgs: string[] = []
        if (jobsRes.status === 'rejected') msgs.push(`ジョブ: ${String(jobsRes.reason)}`)
        if (daemonRes.status === 'rejected') msgs.push(`デーモン: ${String(daemonRes.reason)}`)
        setError(msgs.join(' / '))
      } else {
        setError(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'データの読み込みに失敗しました。')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    const latest = events[0]
    if (latest?.type && (latest.type.startsWith('content') || latest.type.startsWith('proposal'))) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        void loadData(true)
      }, 300)
    }
  }, [events, loadData])

  const repoBoundOrgs = useMemo(() => orgs.filter((o) => o.target_repo_path), [orgs])

  // ConfirmDialog 経由の操作ヘルパー（失敗は再 throw してダイアログを開いたまま）
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
      await loadData(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!orgName) {
      toast.error('対象ワークスペース（組織）を選んでください。')
      return
    }
    setBusy(true)
    try {
      await api('POST', '/api/content-jobs', {
        org_name: orgName,
        kind,
        theme,
        interval_seconds: interval,
        publish_platform: publishPlatform,
        publish_mode: publishMode,
      })
      toast.success(
        publishPlatform
          ? `コンテンツジョブを作成しました（承認時に ${PUBLISH_PLATFORMS[publishPlatform] ?? publishPlatform} へ投稿予約）。`
          : 'コンテンツジョブを作成しました。',
      )
      // テーマのみクリア（org/kind/interval/platform は連続作成で維持）
      setTheme('')
      await loadData(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'ジョブの作成に失敗しました。')
    } finally {
      setBusy(false)
    }
  }

  const toggleJob = async (job: ContentJob) => {
    setTogglingJobId(job.job_id)
    try {
      await api('PATCH', `/api/content-jobs/${job.job_id}`, { enabled: !job.enabled })
      toast.success(job.enabled ? 'ジョブを無効化しました。' : 'ジョブを有効化しました。')
      await loadData(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '更新に失敗しました。')
    } finally {
      setTogglingJobId(null)
    }
  }

  const runNow = async (job: ContentJob) => {
    setRunningJobId(job.job_id)
    try {
      const res = await api<{ ok: boolean; detail: string }>('POST', `/api/content-jobs/${job.job_id}/run`)
      if (res.ok) toast.success(`生成しました: ${res.detail}`)
      else toast.error(`生成に失敗しました: ${res.detail}`)
      await loadData(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '実行に失敗しました。')
    } finally {
      setRunningJobId(null)
    }
  }

  const handleOpenStudio = (job: ContentJob) => {
    // スタジオへ遷移し、ジョブのテーマをタイトルのシードとして渡す。
    // 生成された下書き本文はインボックス（content_asset 提案）にあるため、
    // ここではテーマのみ渡し、インボックスで「スタジオで整える」を使う導線も案内する。
    navigate('/studio', {
      state: {
        title: job.theme || `${KIND_LABELS[job.kind] ?? job.kind}（${job.org_name}）`,
        body: '',
        sourceLabel: 'コンテンツスケジュール',
      },
    })
    toast.info(
      '生成済みの本文はインボックス（コンテンツ下書き提案）にあります。インボックスの「スタジオで整える」から読み込めます。',
      { duration: 6000 },
    )
  }

  const handleDeleteClick = (job: ContentJob) => {
    setConfirm({
      title: 'このジョブを削除しますか？',
      description: (
        <>
          <strong>{job.org_name}</strong> ·{' '}
          {KIND_LABELS[job.kind] ?? job.kind}
          {job.theme ? `「${job.theme}」` : ''}（実行 {job.run_count} 回）を削除します。
          この操作は取り消せません。
        </>
      ),
      confirmLabel: '削除する',
      run: () =>
        directRun(
          () => api('DELETE', `/api/content-jobs/${job.job_id}`),
          'ジョブを削除しました。',
        ),
    })
  }

  const handleDaemon = async (action: 'start' | 'stop') => {
    setBusy(true)
    try {
      await api(
        'POST',
        `/api/content-daemon/${action}`,
        action === 'start' ? { interval: daemonInterval } : undefined,
      )
      toast.success(
        action === 'start'
          ? `PDCA ループを開始しました（${formatInterval(daemonInterval)}ごとに巡回）。`
          : 'PDCA ループを停止しました。',
      )
      await loadData(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title={
          <>
            <CalendarClock size={20} /> コンテンツ・スケジュール
          </>
        }
        subtitle={
          <>
            投稿ドラフトを定期生成し、PDCA で回します。生成物はワークスペース repo 内に
            <strong>承認待ちの下書き</strong>として作られます。承認後に投稿先が設定されている場合のみ外部送信されます。
          </>
        }
        actions={
          <RefreshButton onClick={() => void loadData()} busy={loading} />
        }
      />

      <div className="page-content flex flex-col gap-5">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={() => void loadData()}
          loadingText="コンテンツデータを読み込み中…"
          errorTitle="データの読み込みに失敗しました"
        >
          <>
            {/* PDCA ループ制御 */}
            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`badge ${daemon?.running ? 'badge-green' : 'badge-neutral'}`}>
                      {daemon?.running ? 'PDCA 稼働中' : '停止中'}
                    </span>
                    {daemon?.rate_limited ? (
                      <span className="badge badge-yellow">
                        レート制限で自動停止（再開可: {formatDateTime(daemon.retry_at)}）
                      </span>
                    ) : null}
                    <span className="text-xs text-muted">
                      サイクル {daemon?.cycle_count ?? 0}
                      {daemon?.interval_seconds
                        ? `（${formatInterval(daemon.interval_seconds)}ごと）`
                        : null}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {/* ループ開始時の巡回間隔 */}
                    {!daemon?.running ? (
                      <select
                        className="input"
                        value={daemonInterval}
                        onChange={(e) => setDaemonInterval(Number(e.target.value))}
                        aria-label="巡回間隔"
                      >
                        {DAEMON_INTERVAL_PRESETS.map((p) => (
                          <option key={p.value} value={p.value}>
                            {p.label}ごとに巡回
                          </option>
                        ))}
                      </select>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleDaemon('start')}
                      disabled={busy || daemon?.running}
                    >
                      {busy && !daemon?.running ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Play size={14} />
                      )}
                      ループ開始
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void handleDaemon('stop')}
                      disabled={busy || !daemon?.running}
                    >
                      <Pause size={14} /> 停止
                    </button>
                  </div>
                </div>
                <p className="text-xs text-muted">
                  ループは Claude のレート制限を検知すると自動停止します（無限実行・自己抑制）。
                </p>
              </div>
            </div>

            {/* ジョブ作成 */}
            <div className="card">
              <div className="card-body">
                <h2 className="card-title mb-3">
                  <Plus size={16} /> 定期ジョブを追加
                </h2>

                {repoBoundOrgs.length === 0 ? (
                  <div className="empty-state">
                    <CalendarClock className="empty-state-icon" size={28} />
                    <h3>連携済みワークスペースがありません</h3>
                    <p>
                      コンテンツジョブを追加するには、まず組織にリポジトリ（ワークスペース）を連携してください。
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm mt-2"
                      onClick={() => void navigate('/orgs')}
                    >
                      組織画面へ
                    </button>
                  </div>
                ) : (
                  <form onSubmit={(e) => void handleCreate(e)} className="flex flex-col gap-3">
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="input-group">
                        <label className="input-label" htmlFor="cj-org">
                          対象ワークスペース（組織）
                        </label>
                        <select
                          id="cj-org"
                          className="input"
                          value={orgName}
                          onChange={(e) => setOrgName(e.target.value)}
                        >
                          <option value="">選択してください</option>
                          {repoBoundOrgs.map((o) => (
                            <option key={o.name} value={o.name}>
                              {o.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="input-group">
                        <label className="input-label" htmlFor="cj-kind">
                          種類
                        </label>
                        <select
                          id="cj-kind"
                          className="input"
                          value={kind}
                          onChange={(e) => setKind(e.target.value)}
                        >
                          {Object.entries(KIND_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                        {KIND_DESCRIPTIONS[kind] ? (
                          <p className="text-xs text-muted mt-1">{KIND_DESCRIPTIONS[kind]}</p>
                        ) : null}
                      </div>
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="cj-theme">
                        テーマ{' '}
                        <span className="text-muted font-normal text-xs">
                          （任意・未指定なら組織のデフォルト方針で生成）
                        </span>
                      </label>
                      <input
                        id="cj-theme"
                        className="input"
                        value={theme}
                        onChange={(e) => setTheme(e.target.value)}
                        placeholder="例: 朝の生産性ハック"
                        maxLength={200}
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="cj-interval">
                        生成間隔
                      </label>
                      <select
                        id="cj-interval"
                        className="input"
                        value={interval}
                        onChange={(e) => setIntervalSeconds(Number(e.target.value))}
                      >
                        {INTERVAL_PRESETS.map((p) => (
                          <option key={p.value} value={p.value}>
                            {p.label}ごと
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="input-group">
                        <label className="input-label" htmlFor="cj-platform">
                          投稿先（任意）
                        </label>
                        <select
                          id="cj-platform"
                          className="input"
                          value={publishPlatform}
                          onChange={(e) => setPublishPlatform(e.target.value)}
                        >
                          <option value="">投稿しない（下書きのみ）</option>
                          {Object.entries(PUBLISH_PLATFORMS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </div>
                      {publishPlatform ? (
                        <div className="input-group">
                          <label className="input-label" htmlFor="cj-pubmode">
                            投稿方法
                          </label>
                          <select
                            id="cj-pubmode"
                            className="input"
                            value={publishMode}
                            onChange={(e) => setPublishMode(e.target.value)}
                          >
                            <option value="assisted">承認後に手動送信（補助）</option>
                          </select>
                        </div>
                      ) : null}
                    </div>
                    {publishPlatform ? (
                      <p className="text-xs text-muted">
                        承認すると投稿待ちに入り、投稿画面へ流し込み（最終送信は人間）されます。
                      </p>
                    ) : null}
                    <div>
                      <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={busy || !orgName}
                      >
                        {busy ? (
                          <>
                            <Loader2 size={14} className="animate-spin" /> 追加中…
                          </>
                        ) : (
                          <>
                            <Plus size={14} /> ジョブを追加
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>

            {/* ジョブ一覧 */}
            <div className="card">
              <div className="card-body">
                <h2 className="card-title mb-3">登録ジョブ（{jobs.length}）</h2>
                {jobs.length === 0 ? (
                  <div className="empty-state">
                    <CalendarClock className="empty-state-icon" size={28} />
                    <h3>ジョブがありません</h3>
                    <p>上のフォームから、ワークスペースに対する定期投稿生成ジョブを追加してください。</p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {jobs.map((job) => (
                      <ContentJobCard
                        key={job.job_id}
                        job={job}
                        runningJobId={runningJobId}
                        togglingJobId={togglingJobId}
                        onRunNow={runNow}
                        onToggle={toggleJob}
                        onDelete={handleDeleteClick}
                        onOpenStudio={handleOpenStudio}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 最近のサイクル */}
            {logs.length > 0 ? (
              <div className="card">
                <div className="card-body">
                  <h2 className="card-title mb-3">最近のサイクル</h2>
                  {/* 凡例 */}
                  <div className="flex items-center gap-4 text-xs text-muted mb-2 pb-2 border-b border-white/10">
                    <span>#サイクル 完了時刻</span>
                    <span className="ml-auto">対象(due) / 生成 / 介入(human)</span>
                  </div>
                  <div className="flex flex-col gap-1 text-sm">
                    {logs.slice().reverse().map((log) => {
                      const isAnomaly = (log.generated ?? 0) === 0 && (log.interventions ?? 0) > 0
                      return (
                        <div
                          key={`${log.cycle}-${log.completed_at ?? ''}`}
                          className={`flex items-center justify-between gap-3 text-xs ${
                            isAnomaly ? 'text-yellow-400' : 'text-muted'
                          }`}
                        >
                          <span>
                            #{log.cycle} {formatDateTime(log.completed_at ?? null)}
                          </span>
                          <span>
                            {log.due_jobs ?? 0} / {log.generated ?? 0} / {log.interventions ?? 0}
                            {log.rate_limited ? ' · レート制限' : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            ) : null}
          </>
        </AsyncBoundary>
      </div>

      {/* 削除確認ダイアログ */}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel ?? '実行'}
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </div>
  )
}
