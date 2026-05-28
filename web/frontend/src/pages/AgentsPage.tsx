import { useCallback, useEffect, useState } from 'react'
import { Bot, Cpu, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type Agent = {
  name: string
  capability_id: string
  skills: string[]
  description: string
  implementation: string
}

type Skill = {
  name: string
  description: string
  persona: string
  focus: string
}

type RoutingAnalysis = {
  recommended_agent_ids?: string[]
  complexity?: string
  [key: string]: unknown
}

type RoutingResponse = {
  task_type: string
  analysis: RoutingAnalysis
}

const taskTypeOptions = [
  { value: 'analysis',        label: '分析' },
  { value: 'goal_execution',  label: 'ゴール実行' },
  { value: 'proposal_review', label: '提案レビュー' },
  { value: 'implementation',  label: '実装' },
]

function getComplexityBadge(value: unknown) {
  if (value === 'low')    return { label: '低', cls: 'badge-green' }
  if (value === 'medium') return { label: '中', cls: 'badge-yellow' }
  if (value === 'high')   return { label: '高', cls: 'badge-red' }
  return { label: '不明', cls: 'badge-neutral' }
}

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [taskType, setTaskType] = useState(taskTypeOptions[0].value)
  const [analyzing, setAnalyzing] = useState(false)
  const [routing, setRouting] = useState<RoutingResponse | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [agentData, skillData] = await Promise.all([
        api<Agent[]>('GET', '/api/agents'),
        api<Skill[]>('GET', '/api/skills'),
      ])
      setAgents(agentData)
      setSkills(skillData)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'エージェントとスキルの読み込みに失敗しました。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleAnalyze = async () => {
    setAnalyzing(true)
    try {
      const response = await api<RoutingResponse>(
        'GET',
        `/api/orchestration/analyze/${encodeURIComponent(taskType)}`,
      )
      setRouting(response)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'オーケストレーションの分析に失敗しました。')
    } finally {
      setAnalyzing(false)
    }
  }

  const complexity = routing ? getComplexityBadge(routing.analysis.complexity) : null

  return (
    <>
      <header className="page-header">
        <div className="page-title">エージェント</div>
        <div className="page-actions">
          <span className="badge badge-neutral">{agents.length} エージェント</span>
          <span className="badge badge-blue">{skills.length} スキル</span>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">エージェントレジストリを読み込み中…</div>
            </div>
          </div>
        ) : null}

        {/* ── Agents ─────────────────────────────────────────── */}
        {!loading && (
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">登録済みエージェント</div>
                <div className="card-description">プラットフォームで利用可能な専門エージェント一覧です。</div>
              </div>
            </div>
            <div className="card-body">
              {agents.length === 0 ? (
                <div className="empty-state">
                  <Bot className="empty-state-icon" size={28} />
                  <h3>エージェントが見つかりません</h3>
                  <p>プラットフォームからまだエージェント情報が報告されていません。</p>
                </div>
              ) : (
                <div className="agents-grid">
                  {agents.map((agent) => (
                    <div key={agent.name} className="agent-card">
                      <div className="agent-card-header">
                        <div className="agent-icon">
                          <Bot size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="agent-name">{agent.name}</div>
                          <div className="agent-capability">{agent.capability_id}</div>
                        </div>
                      </div>
                      {agent.description ? (
                        <div className="agent-description">{agent.description}</div>
                      ) : null}
                      {agent.skills.length > 0 ? (
                        <div className="agent-skills">
                          {agent.skills.map((skill) => (
                            <span key={skill} className="skill-tag">{skill}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Skills ─────────────────────────────────────────── */}
        {!loading && (
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">スキルレジストリ</div>
                <div className="card-description">エージェントが保有するスキルの一覧です。</div>
              </div>
            </div>
            <div className="card-body">
              {skills.length === 0 ? (
                <div className="empty-state">
                  <Zap className="empty-state-icon" size={28} />
                  <h3>スキルが見つかりません</h3>
                  <p>プラットフォームからまだスキル情報が報告されていません。</p>
                </div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>スキル名</th>
                        <th>ペルソナ</th>
                        <th>注力領域</th>
                        <th>説明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {skills.map((skill) => (
                        <tr key={skill.name}>
                          <td>
                            <span className="font-semibold">{skill.name}</span>
                          </td>
                          <td>
                            <span className="badge badge-blue text-xs">{skill.persona || '—'}</span>
                          </td>
                          <td>
                            <span className="badge badge-neutral text-xs">{skill.focus || '—'}</span>
                          </td>
                          <td className="text-muted">{skill.description || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Orchestration ───────────────────────────────────── */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">オーケストレーション分析</div>
              <div className="card-description">タスク種別に応じた推奨エージェントを確認します。</div>
            </div>
          </div>
          <div className="card-body flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <select
                className="select"
                style={{ width: 'auto', minWidth: '140px' }}
                value={taskType}
                onChange={(e) => setTaskType(e.target.value)}
              >
                {taskTypeOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleAnalyze}
                disabled={analyzing}
              >
                <Cpu size={14} />
                {analyzing ? '分析中…' : '分析'}
              </button>
            </div>

            {routing ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-muted">複雑さ:</span>
                  <span className={`badge ${complexity?.cls}`}>{complexity?.label}</span>
                  {(routing.analysis.recommended_agent_ids ?? []).length > 0 && (
                    <>
                      <span className="text-sm text-muted">推奨:</span>
                      {(routing.analysis.recommended_agent_ids ?? []).map((id) => (
                        <span key={id} className="badge badge-green mono text-xs">{id}</span>
                      ))}
                    </>
                  )}
                </div>
                <pre className="progress-log">{JSON.stringify(routing.analysis, null, 2)}</pre>
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '24px' }}>
                <Cpu className="empty-state-icon" size={24} />
                <h3>ルーティング未分析</h3>
                <p>タスク種別を選択して「分析」を実行してください。</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
