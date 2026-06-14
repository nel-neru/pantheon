import { useCallback, useEffect, useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Bot, Cpu, Eye, Gauge, X, Zap } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { ScoreBar } from '@/components/ScoreBar'
import { statusLabel, statusBadge } from '@/lib/labels'

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

/** コピーボタン付き Raw JSON 折りたたみ */
function RawJsonAccordion({ payload }: { payload: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const json = JSON.stringify(payload, null, 2)

  const handleCopy = () => {
    void navigator.clipboard.writeText(json).then(() => {
      toast.success('クリップボードにコピーしました')
    })
  }

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
      className="border border-[var(--color-border-subtle)] rounded-md overflow-hidden"
    >
      <summary className="px-3 py-2 text-xs text-muted cursor-pointer select-none flex items-center justify-between gap-2">
        <span>Raw JSON</span>
        {open && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={(e) => { e.preventDefault(); handleCopy() }}
          >
            コピー
          </button>
        )}
      </summary>
      <pre className="bg-[var(--color-bg)] border-t border-[var(--color-border-subtle)] px-3 py-3 font-mono text-xs text-muted leading-relaxed overflow-auto max-h-48 whitespace-pre-wrap break-all">{json}</pre>
    </details>
  )
}

/** 設定オブジェクトを key-value リストで表示。空なら「設定なし」 */
function ConfigKeyValues({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload)
  if (entries.length === 0) {
    return <p className="text-sm text-muted">設定なし</p>
  }
  return (
    <dl className="flex flex-col gap-2">
      {entries.map(([key, val]) => {
        const display =
          typeof val === 'object' && val !== null
            ? JSON.stringify(val)
            : String(val ?? '—')
        return (
          <div key={key} className="flex gap-2 text-sm">
            <dt className="font-semibold text-muted min-w-32 shrink-0">{key}</dt>
            <dd className="mono break-all">{display}</dd>
          </div>
        )
      })}
    </dl>
  )
}

/** 設定をモーダルで表示（視線断絶解消） */
function ConfigModal({
  config,
  onClose,
}: {
  config: ConfigPanel | null
  onClose: () => void
}) {
  return (
    <Dialog.Root open={config !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog">
          <div className="flex items-center justify-between gap-3 mb-4">
            <Dialog.Title className="dialog-title">{config?.title ?? ''}</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" className="btn btn-ghost btn-sm" aria-label="閉じる">
                <X size={14} />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            設定の詳細
          </Dialog.Description>

          {config ? (
            <div className="flex flex-col gap-4">
              <ConfigKeyValues payload={config.payload} />
              <RawJsonAccordion payload={config.payload} />
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** 分析結果の構造化表示 */
function AnalysisDisplay({
  routing,
  runtimeAgents,
  agents,
}: {
  routing: RoutingResponse
  runtimeAgents: RuntimeAgent[]
  agents: Agent[]
}) {
  const complexity = getComplexityBadge(routing.analysis.complexity)
  const recommendedIds = routing.analysis.recommended_agent_ids ?? []

  /** ID から name を解決（runtimeAgents 優先、次に agents） */
  function resolveName(id: string): string {
    const rt = runtimeAgents.find((a) => a.id === id)
    if (rt) return rt.name
    const def = agents.find((a) => a.capability_id === id || a.name === id)
    if (def) return def.name
    return id
  }

  // recommended/complexity 以外の残りのフィールド
  const extraEntries = Object.entries(routing.analysis).filter(
    ([k]) => k !== 'recommended_agent_ids' && k !== 'complexity',
  )

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted">複雑さ:</span>
        <span className={`badge ${complexity.cls}`}>{complexity.label}</span>
        {recommendedIds.length > 0 && (
          <>
            <span className="text-sm text-muted">推奨:</span>
            {recommendedIds.map((id) => {
              const name = resolveName(id)
              return (
                <span key={id} className="badge badge-green text-xs" title={id}>
                  {name === id ? id : `${name} (${id})`}
                </span>
              )
            })}
          </>
        )}
      </div>

      {extraEntries.length > 0 && (
        <dl className="flex flex-col gap-1">
          {extraEntries.map(([key, val]) => {
            const display =
              typeof val === 'object' && val !== null
                ? JSON.stringify(val)
                : String(val ?? '—')
            return (
              <div key={key} className="flex gap-2 text-sm">
                <dt className="font-semibold text-muted min-w-28 shrink-0">{key}</dt>
                <dd className="mono break-all">{display}</dd>
              </div>
            )
          })}
        </dl>
      )}

      <RawJsonAccordion payload={routing.analysis as Record<string, unknown>} />
    </div>
  )
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

  const runningCount = useMemo(
    () => runtimeAgents.filter((a) => a.status === 'running').length,
    [runtimeAgents],
  )
  const idleCount = useMemo(
    () => runtimeAgents.filter((a) => a.status === 'idle').length,
    [runtimeAgents],
  )
  const averageProficiency = useMemo(() => {
    if (runtimeAgents.length === 0) return null
    return runtimeAgents.reduce((total, agent) => total + agent.proficiency, 0) / runtimeAgents.length
  }, [runtimeAgents])

  return (
    <>
      <PageHeader
        title="エージェント"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <span className="badge badge-neutral">{agents.length} 定義</span>
            {runtimeAgents.length > 0 && (
              <>
                <span className="badge badge-blue">稼働 {runningCount}</span>
                <span className="badge badge-green">待機 {idleCount}</span>
              </>
            )}
            {averageProficiency !== null && (
              <span className="badge badge-neutral" title="全ランタイムエージェントの proficiency 平均 (0–100)">
                平均熟練度 {Math.round(averageProficiency)}
              </span>
            )}
            <RefreshButton onClick={() => void loadData()} busy={loading} />
          </div>
        }
      />

      <div className="page-content flex flex-col gap-5">
        <AsyncBoundary
          loading={loading}
          error={loadError}
          onRetry={() => void loadData()}
          loadingText="エージェントレジストリを読み込み中…"
          errorTitle="レジストリの読み込みに失敗しました"
        >
          <>
            {/* 実行中のエージェント */}
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
                          <tr
                            key={agent.id}
                            className={selectedConfig?.title === `${agent.name} のランタイム設定` ? 'bg-[var(--color-surface-2)]' : ''}
                          >
                            <td>
                              <div className="font-semibold">{agent.name}</div>
                              <div className="text-xs text-muted">{agent.current_task ?? '現在のタスクなし'}</div>
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
                              <span className={`badge ${statusBadge(agent.status)}`}>
                                {statusLabel(agent.status)}
                              </span>
                            </td>
                            <td className="w-32">
                              <ScoreBar score={agent.proficiency} label={`${agent.name} 熟練度`} />
                            </td>
                            <td>
                              <button
                                type="button"
                                id="runtime-row-config-view-btn"
                                className="btn btn-ghost btn-sm"
                                onClick={() => setSelectedConfig({
                                  title: `${agent.name} のランタイム設定`,
                                  payload: agent.configuration,
                                })}
                              >
                                <Eye size={14} />
                                設定
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

            {/* 登録済みエージェント定義 */}
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
                    {agents.map((agent) => {
                      const toolCount = (agent.tools ?? []).length
                      return (
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
                            <span className="badge badge-blue text-xs">{agent.implementation || 'yaml'}</span>
                            {toolCount > 0 && (
                              <span
                                className="badge badge-neutral text-xs"
                                title={(agent.tools ?? []).join(', ')}
                              >
                                {toolCount} ツール
                              </span>
                            )}
                          </div>
                          {agent.skills.length > 0 ? (
                            <div className="agent-skills">
                              {agent.skills.map((skill) => (
                                <span key={skill} className="skill-tag">{skill}</span>
                              ))}
                            </div>
                          ) : null}
                          <div className="flex items-center justify-end gap-3 mt-3">
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
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* スキルレジストリ */}
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

            {/* オーケストレーション分析 */}
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
                    className="select w-auto"
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
                    onClick={() => void handleAnalyze()}
                    disabled={analyzing}
                  >
                    <Cpu size={14} />
                    {analyzing ? '分析中…' : '分析'}
                  </button>
                </div>

                {routing ? (
                  <AnalysisDisplay
                    routing={routing}
                    runtimeAgents={runtimeAgents}
                    agents={agents}
                  />
                ) : (
                  <div className="empty-state py-6">
                    <Cpu className="empty-state-icon" size={24} />
                    <h3>ルーティング未分析</h3>
                    <p>タスク種別を選択して「分析」を実行してください。</p>
                  </div>
                )}
              </div>
            </div>
          </>
        </AsyncBoundary>
      </div>

      {/* 設定モーダル（行内視線断絶解消） */}
      <ConfigModal
        config={selectedConfig}
        onClose={() => setSelectedConfig(null)}
      />
    </>
  )
}
