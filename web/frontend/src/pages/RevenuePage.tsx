import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Coins, Eye, RefreshCw, Send, TrendingUp } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type RevenueOrg = {
  org_name: string
  reach: number
  revenue: number
  posts: number
  reach_but_no_revenue: boolean
}

type RevenueMetrics = {
  orgs: RevenueOrg[]
  total_revenue: number
  total_reach: number
}

function fmt(n: number): string {
  return Math.round(n).toLocaleString('ja-JP')
}

export function RevenuePage() {
  const navigate = useNavigate()
  const [data, setData] = useState<RevenueMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api<RevenueMetrics>('GET', '/api/metrics/revenue')
      setData(result)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '収益メトリクスの読み込みに失敗しました。'
      setData(null)
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const orgs = data?.orgs ?? []
  const alerts = orgs.filter((o) => o.reach_but_no_revenue)

  return (
    <>
      <header className="page-header">
        <div className="page-title">収益ダッシュボード</div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">収益メトリクスを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>収益メトリクスの読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && data ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <Coins size={14} />
                    累計収益
                  </div>
                  <div className="metric-value">¥{fmt(data.total_revenue)}</div>
                </div>
              </div>
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <TrendingUp size={14} />
                    累計リーチ
                  </div>
                  <div className="metric-value">{fmt(data.total_reach)}</div>
                </div>
              </div>
              <div className="card">
                <div className="card-body">
                  <div className="metric-label flex items-center gap-1">
                    <Send size={14} />
                    投稿実績（全組織）
                  </div>
                  <div className="metric-value">{fmt(orgs.reduce((sum, o) => sum + o.posts, 0))}</div>
                </div>
              </div>
            </div>

            {alerts.length > 0 ? (
              <div className="card">
                <div className="card-body flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={16} className="text-yellow" />
                    <div className="font-semibold">リーチはあるが収益0の組織（収益化の余地）</div>
                  </div>
                  {alerts.map((o) => (
                    <div key={o.org_name} className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="text-sm">
                        <span className="font-medium">{o.org_name}</span>
                        <span className="text-muted"> ・ リーチ {fmt(o.reach)} / 収益 ¥0</span>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => navigate('/handoffs')}
                      >
                        <Eye size={14} />
                        収益化の引き渡しを確認
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="card">
              <div className="card-body">
                {orgs.length === 0 ? (
                  <div className="empty-state">
                    <Coins className="empty-state-icon" size={28} />
                    <h3>成果データがありません</h3>
                    <p>
                      投稿が公開され、`pantheon hq outcomes` で reach / revenue を記録すると、ここに
                      組織別の収益とリーチが集計されます。
                    </p>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>組織</th>
                        <th className="text-right">リーチ</th>
                        <th className="text-right">収益(¥)</th>
                        <th className="text-right">投稿数</th>
                        <th>状態</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orgs.map((o) => (
                        <tr key={o.org_name}>
                          <td className="font-medium">{o.org_name}</td>
                          <td className="text-right">{fmt(o.reach)}</td>
                          <td className="text-right">{fmt(o.revenue)}</td>
                          <td className="text-right">{fmt(o.posts)}</td>
                          <td>
                            {o.reach_but_no_revenue ? (
                              <span className="badge badge-yellow">収益化の余地</span>
                            ) : o.revenue > 0 ? (
                              <span className="badge badge-green">収益化済み</span>
                            ) : (
                              <span className="badge badge-neutral">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </>
  )
}
