import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BellRing, CheckCheck, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type Notification = {
  id: string
  level: string
  message: string
  org_name: string
  created_at: string
  read: boolean
}

type NotificationSettings = {
  min_level: string
  quiet_hours_start: number
  quiet_hours_end: number
}

const LEVELS = ['info', 'warn', 'critical'] as const

function levelBadge(level: string): string {
  if (level === 'critical') return 'badge-red'
  if (level === 'warn') return 'badge-yellow'
  return 'badge-neutral'
}

export function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([])
  const [unread, setUnread] = useState(0)
  const [settings, setSettings] = useState<NotificationSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, conf] = await Promise.all([
        api<{ items: Notification[]; unread: number }>('GET', '/api/notifications'),
        api<NotificationSettings>('GET', '/api/notifications/settings'),
      ])
      setItems(list.items)
      setUnread(list.unread)
      setSettings(conf)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '通知の読み込みに失敗しました。'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const markRead = useCallback(
    async (id: string) => {
      try {
        await api('POST', `/api/notifications/${encodeURIComponent(id)}/read`)
        await load()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '既読化に失敗しました。')
      }
    },
    [load]
  )

  const markAllRead = useCallback(async () => {
    setBusy(true)
    try {
      const res = await api<{ marked: number }>('POST', '/api/notifications/read-all')
      toast.success(`${res.marked} 件を既読にしました。`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '一括既読に失敗しました。')
    } finally {
      setBusy(false)
    }
  }, [load])

  const saveSettings = useCallback(
    async (patch: Partial<NotificationSettings>) => {
      try {
        const next = await api<NotificationSettings>('PUT', '/api/notifications/settings', patch)
        setSettings(next)
        toast.success('通知設定を保存しました。')
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '設定の保存に失敗しました。')
      }
    },
    []
  )

  return (
    <>
      <header className="page-header">
        <div className="page-title">通知センター</div>
        <div className="page-actions flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy || unread === 0}
            onClick={() => void markAllRead()}
          >
            <CheckCheck size={14} />
            すべて既読
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {/* 設定カード */}
        {settings ? (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="font-semibold">通知設定（時間帯・最小レベル）</div>
              <p className="text-muted text-sm">
                記録は常に残りますが、能動的なプッシュは最小レベル以上・静音時間帯の外でのみ行います
                （開始=終了で静音なし、開始&gt;終了で日跨ぎ）。
              </p>
              <div className="flex items-center gap-4 flex-wrap">
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-muted">最小レベル</span>
                  <select
                    className="select"
                    value={settings.min_level}
                    onChange={(e) => void saveSettings({ min_level: e.target.value })}
                  >
                    {LEVELS.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-muted">静音 開始</span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    className="input"
                    style={{ width: '5rem' }}
                    value={settings.quiet_hours_start}
                    onChange={(e) =>
                      setSettings({ ...settings, quiet_hours_start: Number(e.target.value) })
                    }
                    onBlur={(e) => void saveSettings({ quiet_hours_start: Number(e.target.value) })}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-muted">静音 終了</span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    className="input"
                    style={{ width: '5rem' }}
                    value={settings.quiet_hours_end}
                    onChange={(e) =>
                      setSettings({ ...settings, quiet_hours_end: Number(e.target.value) })
                    }
                    onBlur={(e) => void saveSettings({ quiet_hours_end: Number(e.target.value) })}
                  />
                </label>
              </div>
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">通知を読み込み中…</div>
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
        ) : items.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <BellRing className="empty-state-icon" size={28} />
                <h3>通知はありません</h3>
                <p>健康スコア低下・提案の滞留・公開イベントなどがここに集約されます。</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="text-muted text-sm">未読 {unread} 件 / 全 {items.length} 件</div>
              {items.map((n) => (
                <div
                  key={n.id}
                  className="flex items-center justify-between gap-3 flex-wrap"
                  style={{ opacity: n.read ? 0.55 : 1 }}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`badge ${levelBadge(n.level)}`}>{n.level}</span>
                      {n.org_name ? <span className="text-muted text-sm">{n.org_name}</span> : null}
                      <span className="font-medium truncate">{n.message}</span>
                    </div>
                    <div className="text-xs text-muted mt-1">{n.created_at}</div>
                  </div>
                  {!n.read ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void markRead(n.id)}
                    >
                      <CheckCheck size={14} />
                      既読
                    </button>
                  ) : (
                    <span className="badge badge-neutral">既読</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
