import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarClock, Pause, Play, Plus, RefreshCw, Trash2, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'

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

function formatInterval(seconds: number) {
  if (seconds % 86400 === 0) return `${seconds / 86400}日`
  if (seconds % 3600 === 0) return `${seconds / 3600}時間`
  return `${Math.round(seconds / 60)}分`
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

export function ContentSchedulePage() {
  const [jobs, setJobs] = useState<ContentJob[]>([])
  const [orgs, setOrgs] = useState<OrgOption[]>([])
  const [daemon, setDaemon] = useState<DaemonStatus | null>(null)
  const [logs, setLogs] = useState<CycleLog[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const { events } = usePlatformUpdates()

  const [orgName, setOrgName] = useState('')
  const [kind, setKind] = useState('content_brief')
  const [theme, setTheme] = useState('')
  const [interval, setIntervalSeconds] = useState(86400)
  const [publishPlatform, setPublishPlatform] = useState('')
  const [publishMode, setPublishMode] = useState('assisted')

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    const [jobsRes, orgsRes, daemonRes, logsRes] = await Promise.allSettled([
      api<ContentJob[]>('GET', '/api/content-jobs'),
      api<OrgOption[]>('GET', '/api/organizations'),
      api<DaemonStatus>('GET', '/api/content-daemon/status'),
      api<CycleLog[]>('GET', '/api/content-daemon/logs?limit=10'),
    ])
    if (jobsRes.status === 'fulfilled') setJobs(jobsRes.value)
    if (orgsRes.status === 'fulfilled') setOrgs(orgsRes.value)
    if (daemonRes.status === 'fulfilled') setDaemon(daemonRes.value)
    if (logsRes.status === 'fulfilled') setLogs(logsRes.value)
    setLoading(false)
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    const latest = events[0]
    if (latest?.type && (latest.type.startsWith('content') || latest.type.startsWith('proposal'))) {
      void loadData(true)
    }
  }, [events, loadData])

  const repoBoundOrgs = useMemo(() => orgs.filter((o) => o.target_repo_path), [orgs])

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
      setTheme('')
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ジョブの作成に失敗しました。')
    } finally {
      setBusy(false)
    }
  }

  const toggleJob = async (job: ContentJob) => {
    try {
      await api('PATCH', `/api/content-jobs/${job.job_id}`, { enabled: !job.enabled })
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新に失敗しました。')
    }
  }

  const runNow = async (job: ContentJob) => {
    try {
      const res = await api<{ ok: boolean; detail: string }>('POST', `/api/content-jobs/${job.job_id}/run`)
      if (res.ok) toast.success(`生成しました: ${res.detail}`)
      else toast.error(res.detail)
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '実行に失敗しました。')
    }
  }

  const deleteJob = async (job: ContentJob) => {
    try {
      await api('DELETE', `/api/content-jobs/${job.job_id}`)
      toast.success('ジョブを削除しました。')
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '削除に失敗しました。')
    }
  }

  const handleDaemon = async (action: 'start' | 'stop') => {
    setBusy(true)
    try {
      await api('POST', `/api/content-daemon/${action}`, action === 'start' ? { interval: 600 } : undefined)
      toast.success(action === 'start' ? 'PDCA ループを開始しました。' : 'PDCA ループを停止しました。')
      await loadData(true)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作に失敗しました。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">
            <CalendarClock size={20} /> コンテンツ・スケジュール
          </h1>
          <p className="page-subtitle">
            投稿ドラフトを定期生成し、PDCA で回します。生成物はワークスペース repo 内に
            <strong>承認待ちの下書き</strong>として作られます（外部公開はしません）。
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void loadData()} aria-label="再読み込み">
            <RefreshCw size={14} /> 更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {/* PDCA ループ制御 */}
        <div className="card">
          <div className="card-body flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <span className={`badge ${daemon?.running ? 'badge-green' : 'badge-neutral'}`}>
                  {daemon?.running ? 'PDCA 稼働中' : '停止中'}
                </span>
                {daemon?.rate_limited ? (
                  <span className="badge badge-yellow">
                    レート制限で自動停止（再開可: {formatDateTime(daemon.retry_at)}）
                  </span>
                ) : null}
                {daemon?.pid ? <span className="text-xs text-muted">PID {daemon.pid}</span> : null}
                <span className="text-xs text-muted">サイクル {daemon?.cycle_count ?? 0}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => handleDaemon('start')}
                  disabled={busy || daemon?.running}
                >
                  <Play size={14} /> ループ開始
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleDaemon('stop')}
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
            <form onSubmit={handleCreate} className="flex flex-col gap-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="input-group">
                  <label className="input-label" htmlFor="cj-org">対象ワークスペース（組織）</label>
                  <select id="cj-org" className="input" value={orgName} onChange={(e) => setOrgName(e.target.value)}>
                    <option value="">選択してください</option>
                    {repoBoundOrgs.map((o) => (
                      <option key={o.name} value={o.name}>{o.name}</option>
                    ))}
                  </select>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="cj-kind">種類</label>
                  <select id="cj-kind" className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
                    {Object.entries(KIND_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="input-group">
                <label className="input-label" htmlFor="cj-theme">テーマ</label>
                <input
                  id="cj-theme"
                  className="input"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  placeholder="例: 朝の生産性ハック"
                />
              </div>
              <div className="input-group">
                <label className="input-label" htmlFor="cj-interval">生成間隔</label>
                <select
                  id="cj-interval"
                  className="input"
                  value={interval}
                  onChange={(e) => setIntervalSeconds(Number(e.target.value))}
                >
                  {INTERVAL_PRESETS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}ごと</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="input-group">
                  <label className="input-label" htmlFor="cj-platform">投稿先（任意）</label>
                  <select
                    id="cj-platform"
                    className="input"
                    value={publishPlatform}
                    onChange={(e) => setPublishPlatform(e.target.value)}
                  >
                    <option value="">投稿しない（下書きのみ）</option>
                    {Object.entries(PUBLISH_PLATFORMS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                {publishPlatform ? (
                  <div className="input-group">
                    <label className="input-label" htmlFor="cj-pubmode">投稿方法</label>
                    <select
                      id="cj-pubmode"
                      className="input"
                      value={publishMode}
                      onChange={(e) => setPublishMode(e.target.value)}
                    >
                      <option value="assisted">承認後に手動送信（補助）</option>
                      <option value="auto">承認したら自動投稿</option>
                    </select>
                  </div>
                ) : null}
              </div>
              {publishPlatform ? (
                <p className="text-xs text-muted">
                  承認すると投稿待ちに入り、{publishMode === 'auto' ? '予約時刻に自動投稿' : '投稿画面へ流し込み（最終送信は人間）'}されます。
                </p>
              ) : null}
              <div>
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  <Plus size={14} /> ジョブを追加
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* ジョブ一覧 */}
        <div className="card">
          <div className="card-body">
            <h2 className="card-title mb-3">登録ジョブ（{jobs.length}）</h2>
            {loading ? (
              <p className="text-muted">読み込み中…</p>
            ) : jobs.length === 0 ? (
              <div className="empty-state">
                <CalendarClock className="empty-state-icon" size={28} />
                <h3>ジョブがありません</h3>
                <p>上のフォームから、ワークスペースに対する定期投稿生成ジョブを追加してください。</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {jobs.map((job) => (
                  <div key={job.job_id} className="rounded-xl border border-white/10 p-3 flex flex-col gap-2">
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
                            投稿: {PUBLISH_PLATFORMS[job.publish_platform] ?? job.publish_platform}
                            {job.publish_mode === 'auto' ? '（自動）' : ''}
                          </span>
                        ) : null}
                        <span className="badge badge-blue">実行 {job.run_count}</span>
                      </div>
                    </div>
                    <div className="text-xs text-muted">
                      最終: {formatDateTime(job.last_run_at)}（{job.last_status}） / 次回: {formatDateTime(job.next_run_at)}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => runNow(job)}>
                        <Zap size={13} /> 今すぐ生成
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => toggleJob(job)}>
                        {job.enabled ? <Pause size={13} /> : <Play size={13} />}
                        {job.enabled ? '無効化' : '有効化'}
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => deleteJob(job)}>
                        <Trash2 size={13} /> 削除
                      </button>
                    </div>
                  </div>
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
              <div className="flex flex-col gap-1 text-sm">
                {logs.slice().reverse().map((log) => (
                  <div key={log.cycle} className="flex items-center justify-between gap-3 text-xs text-muted">
                    <span>#{log.cycle} {formatDateTime(log.completed_at ?? null)}</span>
                    <span>
                      対象 {log.due_jobs ?? 0} / 生成 {log.generated ?? 0} / 介入 {log.interventions ?? 0}
                      {log.rate_limited ? ' · レート制限' : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
