import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link2, Plug, RefreshCw, Unplug } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { formatDateTime } from '@/lib/utils'

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

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

export function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

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
      // エラー表示は下の error UI が担うため、toast は出さない（二重通知防止）。
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
        toast.info(
          'ログインを確認できませんでした。ブラウザでログインを完了してから再度お試しください。',
        )
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

      if (status === 'login_started' || status === 'login_in_progress') {
        // 外部ブラウザが開く旨をユーザーに案内してからポーリング開始。
        toast.info(`${detail} ブラウザが開きます。ログインを完了してください。`)
        startPoller(platform)
      } else if (status === 'unsupported' || status === 'unavailable') {
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

  // ConfirmDialog 経由の破壊操作用。失敗時は再 throw してダイアログを開いたままにする。
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
      await load(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const requestDisconnect = (platform: string) => {
    setConfirm({
      title: `${platformLabel(platform)} の接続を切断しますか？`,
      description: (
        <>
          セッション情報を削除します。<strong>再投稿には再ログインが必要です。</strong>
        </>
      ),
      confirmLabel: '切断する',
      run: async () => {
        stopPoller(platform)
        setActionId(`disconnect:${platform}`)
        try {
          await directRun(
            () => api<DisconnectResponse>('DELETE', `/api/publishing/connections/${encodeURIComponent(platform)}`),
            `${platformLabel(platform)} の接続を切断しました。`,
          )
        } finally {
          setActionId(null)
        }
      },
    })
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">プラットフォーム接続</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            aria-label="接続状態を再取得"
            onClick={() => void load()}
            disabled={loading || !!actionId}
          >
            <RefreshCw size={14} aria-hidden />
            {loading ? '更新中…' : '更新'}
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
                <Link2 className="empty-state-icon" size={28} />
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
                <h3>接続先プラットフォームがありません</h3>
                <p>サーバー設定を確認するか、更新してください。</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  更新
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error
          ? connections.map((conn) => {
              const isConnected = conn.status === 'connected'
              const isPolling = pollingPlatforms.has(conn.platform)
              const disconnectBusy = actionId === `disconnect:${conn.platform}`

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
                              別ウィンドウでログインしてください
                            </span>
                          ) : null}
                          <span className="font-semibold">{platformLabel(conn.platform)}</span>
                        </div>
                        <div className="text-sm text-muted">
                          {isConnected
                            ? `接続日時: ${formatDateTime(conn.connected_at)}`
                            : 'ログインしてセッションを確立してください。'}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {isConnected ? (
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => requestDisconnect(conn.platform)}
                            disabled={!!actionId}
                          >
                            <Unplug size={14} />
                            {disconnectBusy ? '切断中…' : '切断'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => void handleConnect(conn.platform)}
                            disabled={!!actionId}
                          >
                            <Plug size={14} />
                            {actionId === `connect:${conn.platform}` ? '接続中…' : '接続'}
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
