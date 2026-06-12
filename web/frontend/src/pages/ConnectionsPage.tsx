import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Link2, Plug, RefreshCw, Unplug } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type ConnectionStatus = 'connected' | 'disconnected'

type Connection = {
  platform: string
  status: ConnectionStatus
  connected_at: string | null
}

type LoginResponse = {
  platform: string
  status: 'login_started' | 'login_in_progress' | 'unsupported' | 'unavailable'
  detail: string
}

type DisconnectResponse = {
  platform: string
  cleared: boolean
  status: 'disconnected'
}

const PLATFORM_LABELS: Record<string, string> = {
  note: 'note',
  x: 'X (Twitter)',
  wordpress: 'WordPress',
}

const POLL_INTERVAL_MS = 3000
const POLL_TIMEOUT_MS = 120_000

function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform
}

function formatConnectedAt(connectedAt: string | null): string {
  if (!connectedAt) return '—'
  try {
    return new Date(connectedAt).toLocaleString('ja-JP')
  } catch {
    return connectedAt
  }
}

export function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)

  // pollerRefs: platform -> { intervalId, timeoutId }
  const pollerRefs = useRef<Map<string, { intervalId: ReturnType<typeof setInterval>; timeoutId: ReturnType<typeof setTimeout> }>>(new Map())
  // ref の変更は再レンダーを起こさないため、バッジ表示用に state へミラーする
  // （タイムアウト経路は setConnections を伴わず、ref だけだとバッジが残留する）。
  const [pollingPlatforms, setPollingPlatforms] = useState<ReadonlySet<string>>(new Set())

  const stopPoller = useCallback((platform: string) => {
    const poller = pollerRefs.current.get(platform)
    if (poller) {
      clearInterval(poller.intervalId)
      clearTimeout(poller.timeoutId)
      pollerRefs.current.delete(platform)
      setPollingPlatforms((prev) => {
        const next = new Set(prev)
        next.delete(platform)
        return next
      })
    }
  }, [])

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const data = await api<Connection[]>('GET', '/api/publishing/connections')
      setConnections(data)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'プラットフォーム接続情報の読み込みに失敗しました。'
      setConnections([])
      setError(message)
      toast.error(message)
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  // Start polling for a specific platform until it becomes connected or times out.
  const startPoller = useCallback(
    (platform: string) => {
      // Guard against stacking pollers for the same platform.
      if (pollerRefs.current.has(platform)) return

      const intervalId = setInterval(async () => {
        try {
          const data = await api<Connection[]>('GET', '/api/publishing/connections')
          setConnections(data)
          const conn = data.find((c) => c.platform === platform)
          if (conn?.status === 'connected') {
            stopPoller(platform)
          }
        } catch {
          // swallow poll errors silently; the user initiated the flow
        }
      }, POLL_INTERVAL_MS)

      const timeoutId = setTimeout(() => {
        stopPoller(platform)
      }, POLL_TIMEOUT_MS)

      pollerRefs.current.set(platform, { intervalId, timeoutId })
      setPollingPlatforms((prev) => new Set(prev).add(platform))
    },
    [stopPoller],
  )

  useEffect(() => {
    void load()
    return () => {
      // Clear all pollers on unmount to prevent memory leaks / stale setStates.
      for (const platform of pollerRefs.current.keys()) {
        stopPoller(platform)
      }
    }
  }, [load, stopPoller])

  const handleConnect = async (platform: string) => {
    if (actionId) return
    setActionId(`connect:${platform}`)
    try {
      const response = await api<LoginResponse>('POST', `/api/publishing/connections/${encodeURIComponent(platform)}/login`)
      const { status, detail } = response

      if (status === 'login_started') {
        toast.info(detail)
        startPoller(platform)
      } else if (status === 'login_in_progress') {
        toast.info(detail)
        startPoller(platform)
      } else if (status === 'unsupported') {
        toast.error(detail)
      } else if (status === 'unavailable') {
        toast.error(detail)
      } else {
        toast.info(detail)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '接続開始に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  const handleDisconnect = async (platform: string) => {
    if (actionId) return
    setActionId(`disconnect:${platform}`)
    stopPoller(platform)
    try {
      await api<DisconnectResponse>('DELETE', `/api/publishing/connections/${encodeURIComponent(platform)}`)
      toast.success(`${platformLabel(platform)} の接続を切断しました。`)
      await load(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '切断に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">プラットフォーム接続</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <div className="card">
          <div className="card-body">
            <p className="text-sm text-muted">
              資格情報（パスワード等）は保存されません。ログイン後のブラウザセッション（storage_state）のみ{' '}
              <code className="mono">~/.pantheon</code> に保存されます。
            </p>
          </div>
        </div>

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">接続情報を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>接続情報の読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && connections.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <Link2 className="empty-state-icon" size={28} />
                <h3>プラットフォームが見つかりません</h3>
                <p>サーバーから接続先プラットフォームが返されませんでした。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error
          ? connections.map((conn) => {
              const isConnected = conn.status === 'connected'
              const isPolling = pollingPlatforms.has(conn.platform)
              const connectBusy = actionId === `connect:${conn.platform}`
              const disconnectBusy = actionId === `disconnect:${conn.platform}`
              const anyBusy = connectBusy || disconnectBusy

              return (
                <div key={conn.platform} className="card">
                  <div className="card-body">
                    <div className="flex items-center gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className={`badge ${isConnected ? 'badge-green' : 'badge-neutral'}`}>
                            {isConnected ? '接続済み' : '未接続'}
                          </span>
                          {isPolling && !isConnected ? (
                            <span className="badge badge-yellow flex items-center gap-1">
                              <div className="spinner w-2.5 h-2.5" />
                              ログイン待機中
                            </span>
                          ) : null}
                          <span className="font-semibold">{platformLabel(conn.platform)}</span>
                        </div>
                        <div className="text-sm text-muted">
                          {isConnected ? `接続日時: ${formatConnectedAt(conn.connected_at)}` : 'ログインしてセッションを確立してください。'}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {isConnected ? (
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => void handleDisconnect(conn.platform)}
                            disabled={anyBusy}
                          >
                            <Unplug size={14} />
                            {disconnectBusy ? '切断中…' : '切断'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => void handleConnect(conn.platform)}
                            disabled={anyBusy || !!actionId}
                          >
                            <Plug size={14} />
                            {connectBusy ? '接続中…' : '接続'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          : null}
      </div>
    </>
  )
}
