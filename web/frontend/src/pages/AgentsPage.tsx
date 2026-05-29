import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Bot, Cpu, Eye, Gauge, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type Agent = {
  name: string
  capability_id: string
  skills: string[]
  description: string
  implementation: string
  tools?: string[]
  behavior?: string
  schema_version?: string
  configuration?: Record<string, unknown>
}

type RuntimeAgent = {
  id: string
  name: string
  organization: string
  division: string
  team: string
  skills: string[]
  status: string
  current_task?: string | null
  proficiency: number
  configuration: Record<string, unknown>
}

type Skill = {
  id?: string
  name: string
  description: string
  persona: string
  focus: string
  schema_version?: string
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

type ConfigPanel = {
  title: string
  payload: Record<string, unknown>
}

const taskTypeOptions = [
  { value: 'analysis', label: '分析' },
  { value: 'goal_execution', label: 'ゴール実行' },
  { value: 'proposal_review', label: '提案レビュー' },
  { value: 'implementation', label: '実装' },
]

function getComplexityBadge(value: unknown) {
  if (value === 'low') return { label: '低', cls: 'badge-green' }
  if (value === 'medium') return { label: '中', cls: 'badge-yellow' }
  if (value === 'high') return { label: '高', cls: 'badge-red' }
  return { label: '不明', cls: 'badge-neutral' }
}

function statusBadge(status: string) {
  if (status === 'running') return 'badge-blue'
  if (status === 'idle') return 'badge-green'
  return 'badge-neutral'
}

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [runtimeAgents, setRuntimeAgents] = useState<RuntimeAgent[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [taskType, setTaskType] = useState(taskTypeOptions[0].value)
  const [analyzing, setAnalyzing] = useState(false)
  const [routing, setRouting] = useState<RoutingResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedConfig, setSelectedConfig] = useState<ConfigPanel | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [agentResult, skillResult, runtimeResult] = await Promise.allSettled([
        api<Agent[]>('GET', '/api/agents'),
        api<Skill[]>('GET', '/api/skills'),
        api<RuntimeAgent[]>('GET', '/api/agents/runtime'),
      ])

      if (agentResult.status === 'rejected') {
        throw agentResult.reason
      }
      if (skillResult.status === 'rejected') {
        throw skillResult.reason
      }

      setAgents(agentResult.value)
      setSkills(skillResult.value)
      setRuntimeAgents(runtimeResult.status === 'fulfilled' ? runtimeResult.value : [])
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'エージェントとスキルの読み込みに失敗しました。'
      setAgents([])
      setSkills([])
      setRuntimeAgents([])
      setSelectedConfig(null)
      setLoadError(message)
      toast.error(message)
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
  const averageProficiency = useMemo(() => {
    if (runtimeAgents.length === 0) return 0
    return runtimeAgents.reduce((total, agent) => total + agent.proficiency, 0) / runtimeAgents.length
  }, [runtimeAgents])

  return (
    <>
      <header className="page-header">
        <div className="page-title">エージェント</div>
        <div className="page-actions">
          <span className="badge badge-neutral">{agents.length} 定義</span>
          <span className="badge badge-blue">{runtimeAgents.length} 稼働中/待機</span>
          <span className="badge badge-green">平均熟練度 {Math.round(averageProficiency)}</span>
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

        {!loading && loadError ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>レジストリの読み込みに失敗しました</h3>
                <p>{loadError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadData()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !loadError && (
          <div className="grid-2">
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">実行中のエージェント</div>
                  <div className="card-description">組織に配備されたエージェントの状態と熟練度を確認できます。</div>
                </div>
              </div>
              <div className="card-body">
                {runtimeAgents.length === 0 ? (
                  <div className="empty-state">
                    <Gauge className="empty-state-icon" size={28} />
                    <h3>ランタイムエージェントがありません</h3>
                    <p>組織を作成すると、ここに Division / Team 配下のエージェントが表示されます。</p>
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>エージェント</th>
                          <th>所属</th>
                          <th>スキル</th>
                          <th>状態</th>
                          <th>熟練度</th>
                          <th>設定</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runtimeAgents.map((agent) => (
                          <tr key={agent.id}>
                            <td>
                              <div className="font-semibold">{agent.name}</div>
                              <div className="text-xs text-muted">{agent.current_task || '現在のタスクなし'}</div>
                            </td>
                            <td>
                              <div>{agent.organization}</div>
                              <div className="text-xs text-muted">{agent.division} / {agent.team}</div>
                            </td>
                            <td>
                              <div className="flex flex-wrap gap-1">
                                {agent.skills.map((skill) => (
                                  <span key={skill} className="skill-tag">{skill}</span>
                                ))}
                              </div>
                            </td>
                            <td>
                              <span className={`badge ${statusBadge(agent.status)}`}>{agent.status}</span>
                            </td>
                            <td>
                              <div className="flex flex-col gap-2" style={{ minWidth: '120px' }}>
                                <div className="mono text-sm">{Math.round(agent.proficiency)}</div>
                                <div className="health-track">
                                  <div
                                    className="health-fill good"
                                    style={{ width: `${Math.max(0, Math.min(100, agent.proficiency))}%` }}
                                  />
                                </div>
                              </div>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() => setSelectedConfig({
                                  title: `${agent.name} のランタイム設定`,
                                  payload: agent.configuration,
                                })}
                              >
                                <Eye size={14} />
                                表示
                              </button>
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
                  <div className="card-title">設定ビューア</div>
                  <div className="card-description">エージェント定義やランタイム構成を JSON で確認できます。</div>
                </div>
              </div>
              <div className="card-body">
                {selectedConfig ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold">{selectedConfig.title}</div>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelectedConfig(null)}>
                        閉じる
                      </button>
                    </div>
                    <pre className="progress-log">{JSON.stringify(selectedConfig.payload, null, 2)}</pre>
                  </div>
                ) : (
                  <div className="empty-state" style={{ padding: '24px' }}>
                    <Eye className="empty-state-icon" size={24} />
                    <h3>設定を選択してください</h3>
                    <p>「表示」ボタンから YAML 定義またはランタイム設定を確認できます。</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {!loading && !loadError && (
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">登録済みエージェント定義</div>
                <div className="card-description">YAML で管理されるエージェント設定の一覧です。</div>
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
                      {agent.description ? <div className="agent-description">{agent.description}</div> : null}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="badge badge-neutral text-xs">schema {agent.schema_version || 'legacy'}</span>
                        <span className="badge badge-blue text-xs">{agent.implementation || 'yaml'}</span>
                      </div>
                      {agent.skills.length > 0 ? (
                        <div className="agent-skills">
                          {agent.skills.map((skill) => (
                            <span key={skill} className="skill-tag">{skill}</span>
                          ))}
                        </div>
                      ) : null}
                      <div className="flex items-center justify-between gap-3 mt-3">
                        <span className="text-xs text-muted">{(agent.tools ?? []).length} tools</span>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setSelectedConfig({
                            title: `${agent.name} の定義`,
                            payload: {
                              capability_id: agent.capability_id,
                              schema_version: agent.schema_version,
                              description: agent.description,
                              configuration: agent.configuration ?? {},
                            },
                          })}
                        >
                          <Eye size={14} />
                          設定を見る
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {!loading && !loadError && (
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
                        <tr key={skill.id ?? skill.name}>
                          <td>
                            <div className="font-semibold">{skill.name}</div>
                            <div className="text-xs text-muted">schema {skill.schema_version || 'legacy'}</div>
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
