import { useCallback, useEffect, useState } from 'react'
import { ArrowRightLeft, Boxes, Cpu } from 'lucide-react'

import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
import { api } from '@/lib/api'

type OrchestraAgent = {
  agent_id: string | null
  title: string | null
  role?: string | null
  status: string
  exit_code?: number | null
}

type OrchestraSession = {
  id: string
  name: string
  status: string
  driver: string
  agents: OrchestraAgent[]
}

type OrchestraHandoff = {
  id: string
  source: string
  target: string
  kind: string
  status: string
  title: string
  priority?: string
}

type OrchestraCounts = {
  sessions: number
  active_sessions: number
  agents: number
  handoffs: number
  pending_handoffs: number
}

type OrchestraData = {
  sessions: OrchestraSession[]
  handoffs: OrchestraHandoff[]
  counts: OrchestraCounts
}

const EMPTY: OrchestraData = {
  sessions: [],
  handoffs: [],
  counts: { sessions: 0, active_sessions: 0, agents: 0, handoffs: 0, pending_handoffs: 0 },
}

function statusBadge(status: string) {
  if (status === 'running') return 'badge-blue'
  if (['done', 'completed', 'consumed', 'approved'].includes(status)) return 'badge-green'
  if (['failed', 'error', 'rejected'].includes(status)) return 'badge-red'
  if (['pending', 'rate_limited'].includes(status)) return 'badge-yellow'
  return 'badge-neutral'
}

/**
 * オーケストラ可視化。実行中セッション×エージェントのライブツリーと、組織横断の
 * handoff フライホイール（集客→販売→収益化）を表示する。/ws/updates の session 系
 * イベントで再取得してライブ更新する。取得失敗時は黙って空表示にし、Dashboard 全体を妨げない。
 */
export function OrchestraView() {
  const [data, setData] = useState<OrchestraData>(EMPTY)
  const [loaded, setLoaded] = useState(false)
  const { events } = usePlatformUpdates()

  const load = useCallback(async () => {
    try {
      const result = await api<OrchestraData>('GET', '/api/dashboard/orchestra')
      setData({
        sessions: result?.sessions ?? [],
        handoffs: result?.handoffs ?? [],
        counts: result?.counts ?? EMPTY.counts,
      })
    } catch {
      setData(EMPTY)
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const latest = events[0]
    const type = latest?.type ?? ''
    if (type.startsWith('session') || type.startsWith('handoff') || type === 'task_dispatched') {
      void load()
    }
  }, [events, load])

  const { sessions, handoffs, counts } = data

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">オーケストラ</div>
          <div className="card-description">
            実行中セッション×エージェントと組織横断フライホイールのライブビューです。
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-blue">{counts.active_sessions} 実行中</span>
          <span className="badge badge-neutral">{counts.agents} エージェント</span>
        </div>
      </div>
      <div className="card-body flex flex-col gap-5">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted mb-2">
            <Boxes size={14} /> セッション ({counts.sessions})
          </div>
          {sessions.length === 0 ? (
            <div className="text-sm text-muted">
              {loaded
                ? '実行中のセッションはありません。wmux のチャットで /analyze や /goal を実行すると表示されます。'
                : '読み込み中…'}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="rounded-xl border border-white/10 p-3 flex flex-col gap-2"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="font-semibold">{session.name}</div>
                    <div className="flex items-center gap-2">
                      <span className="badge badge-neutral">{session.driver}</span>
                      <span className={`badge ${statusBadge(session.status)}`}>{session.status}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {session.agents.length === 0 ? (
                      <span className="text-xs text-muted">エージェントなし</span>
                    ) : (
                      session.agents.map((agent) => (
                        <span
                          key={agent.agent_id ?? agent.title}
                          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1"
                        >
                          <Cpu size={12} />
                          <span className="text-xs">{agent.title}</span>
                          <span className={`badge ${statusBadge(agent.status)}`}>{agent.status}</span>
                        </span>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center gap-2 text-sm text-muted mb-2">
            <ArrowRightLeft size={14} /> フライホイール ({counts.handoffs} 件 / 承認待ち{' '}
            {counts.pending_handoffs})
          </div>
          {handoffs.length === 0 ? (
            <div className="text-sm text-muted">組織横断の引き渡しはまだありません。</div>
          ) : (
            <div className="flex flex-col gap-2">
              {handoffs.map((handoff) => (
                <div key={handoff.id} className="flex items-center gap-2 flex-wrap">
                  <span className="badge badge-neutral">{handoff.source}</span>
                  <ArrowRightLeft size={12} />
                  <span className="badge badge-neutral">{handoff.target}</span>
                  <span className="text-sm truncate flex-1" title={handoff.title}>
                    {handoff.title}
                  </span>
                  <span className={`badge ${statusBadge(handoff.status)}`}>{handoff.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
