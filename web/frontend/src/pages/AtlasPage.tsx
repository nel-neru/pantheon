import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  GitBranch,
  LayoutGrid,
  Map as MapIcon,
  Network,
  Route as RouteIcon,
  Terminal,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

type FlowStatus = 'solid' | 'partial' | 'fragile' | 'unknown'

type KnownIssue = {
  severity: 'high' | 'medium' | 'low'
  title: string
  detail?: string
  file?: string
}

type Flow = {
  id: string
  name: string
  summary: string
  trigger: { kind: string; name: string }
  steps: { component: string; action: string }[]
  surfaces: string[]
  state?: string[]
  verification?: string[]
  status: FlowStatus
  known_issues?: KnownIssue[]
}

type CliArg = { name: string; required: boolean; help: string }
type CliCommand = { command: string; group: string; handler: string | null; help: string; args: CliArg[] }
type ApiRoute = { path: string; methods: string[]; name: string; kind: 'rest' | 'websocket' | 'error'; tags: string[] }
type GraphNode = { id: string; label: string; files: number }
type GraphEdge = { source: string; target: string; weight: number }
type Subsystem = { id: string; label: string; purpose: string; paths: string[]; files: number; lines: number }

type AtlasModel = {
  generated_at: string
  overview: {
    flows: number
    cli_commands: number
    api_routes: number
    websockets: number
    pages: number
    subsystems: number
    modules: number
    total_lines: number
    total_files: number
  }
  flows: Flow[]
  cli: CliCommand[]
  api: ApiRoute[]
  frontend: { nav: { to: string; label: string }[]; routes: { path: string; element: string }[]; pages: { name: string; path: string; lines: number }[] }
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; file_count: number }
  subsystems: Subsystem[]
}

type TabKey = 'flows' | 'graph' | 'cli' | 'api' | 'subsystems'

const TABS: { key: TabKey; label: string; icon: typeof MapIcon }[] = [
  { key: 'flows', label: '使用フロー', icon: GitBranch },
  { key: 'graph', label: '依存グラフ', icon: Network },
  { key: 'cli', label: 'CLI', icon: Terminal },
  { key: 'api', label: 'API', icon: RouteIcon },
  { key: 'subsystems', label: 'サブシステム', icon: LayoutGrid },
]

const STATUS_META: Record<FlowStatus, { label: string; cls: string }> = {
  solid: { label: '安定', cls: 'badge-green' },
  partial: { label: '一部課題', cls: 'badge-yellow' },
  fragile: { label: '要注意', cls: 'badge-red' },
  unknown: { label: '不明', cls: 'badge-neutral' },
}

const SEVERITY_CLS: Record<string, string> = {
  high: 'badge-red',
  medium: 'badge-yellow',
  low: 'badge-neutral',
}

function methodBadge(method: string): string {
  if (method === 'GET') return 'badge-green'
  if (method === 'POST') return 'badge-blue'
  if (method === 'PUT' || method === 'PATCH') return 'badge-yellow'
  if (method === 'DELETE') return 'badge-red'
  return 'badge-neutral'
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card">
      <div className="card-body flex flex-col gap-1">
        <div className="text-2xl font-semibold mono">{value}</div>
        <div className="text-xs text-muted">{label}</div>
      </div>
    </div>
  )
}

// ---- Dependency graph (subsystem level) rendered as a hand-rolled SVG -------

function DependencyGraph({ graph }: { graph: AtlasModel['graph'] }) {
  const [hovered, setHovered] = useState<string | null>(null)
  const width = 760
  const height = 520
  const cx = width / 2
  const cy = height / 2
  const radius = 190
  const nodes = graph.nodes
  const maxFiles = Math.max(1, ...nodes.map((n) => n.files))
  const maxWeight = Math.max(1, ...graph.edges.map((e) => e.weight))

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>()
    nodes.forEach((node, index) => {
      const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2
      map.set(node.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) })
    })
    return map
  }, [nodes, cx, cy])

  if (nodes.length === 0) {
    return <div className="empty-state"><Network className="empty-state-icon" size={24} /><h3>グラフデータがありません</h3></div>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm text-muted">
        ノード = サブシステム（円の大きさ ∝ ファイル数）、線 = import 依存（太さ ∝ 依存数）。ノードにホバーすると関連だけ強調します。
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="サブシステム依存グラフ" className="atlas-graph">
        {graph.edges.map((edge, i) => {
          const a = positions.get(edge.source)
          const b = positions.get(edge.target)
          if (!a || !b) return null
          const active = hovered === null || hovered === edge.source || hovered === edge.target
          return (
            <line
              key={`${edge.source}-${edge.target}-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="currentColor"
              strokeWidth={1 + (edge.weight / maxWeight) * 5}
              strokeOpacity={active ? 0.45 : 0.06}
            />
          )
        })}
        {nodes.map((node) => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const r = 12 + Math.sqrt(node.files / maxFiles) * 22
          const active = hovered === null || hovered === node.id
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              className="atlas-graph-node"
            >
              <circle cx={pos.x} cy={pos.y} r={r} fillOpacity={active ? 0.85 : 0.25} />
              <text x={pos.x} y={pos.y - r - 6} textAnchor="middle" className="atlas-graph-label">
                {node.label}
              </text>
              <text x={pos.x} y={pos.y + 4} textAnchor="middle" className="atlas-graph-count">
                {node.files}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------

export function AtlasPage() {
  const [atlas, setAtlas] = useState<AtlasModel | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>('flows')
  const [cliFilter, setCliFilter] = useState('')
  const [apiFilter, setApiFilter] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await api<AtlasModel>('GET', '/api/atlas')
      setAtlas(data)
      setError(null)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Atlas の読み込みに失敗しました。'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const statusCounts = useMemo(() => {
    const counts: Record<FlowStatus, number> = { solid: 0, partial: 0, fragile: 0, unknown: 0 }
    atlas?.flows.forEach((f) => {
      counts[f.status] = (counts[f.status] ?? 0) + 1
    })
    return counts
  }, [atlas])

  const filteredCli = useMemo(() => {
    if (!atlas) return []
    const q = cliFilter.trim().toLowerCase()
    const handled = atlas.cli.filter((c) => c.handler)
    if (!q) return handled
    return handled.filter((c) => c.command.toLowerCase().includes(q) || c.help.toLowerCase().includes(q))
  }, [atlas, cliFilter])

  const filteredApi = useMemo(() => {
    if (!atlas) return []
    const q = apiFilter.trim().toLowerCase()
    if (!q) return atlas.api
    return atlas.api.filter((r) => r.path.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
  }, [atlas, apiFilter])

  return (
    <>
      <header className="page-header">
        <div className="flex items-center gap-2">
          <MapIcon size={18} />
          <div className="page-title">Atlas — リポジトリ俯瞰</div>
        </div>
        <div className="page-actions">
          {atlas ? (
            <>
              <span className="badge badge-green">{statusCounts.solid} 安定</span>
              <span className="badge badge-yellow">{statusCounts.partial} 一部課題</span>
              <span className="badge badge-red">{statusCounts.fragile} 要注意</span>
            </>
          ) : null}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()} disabled={loading}>
            再読み込み
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-5">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">リポジトリを解析中…</div>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>Atlas の読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !error && atlas ? (
          <>
            <div className="grid-4">
              <StatCard label="使用フロー" value={atlas.overview.flows} />
              <StatCard label="CLI コマンド" value={atlas.overview.cli_commands} />
              <StatCard label={`API ルート (+WS ${atlas.overview.websockets})`} value={atlas.overview.api_routes} />
              <StatCard label="UI ページ" value={atlas.overview.pages} />
              <StatCard label="サブシステム" value={atlas.overview.subsystems} />
              <StatCard label="モジュール" value={atlas.overview.modules} />
              <StatCard label="総ファイル数" value={atlas.overview.total_files} />
              <StatCard label="総行数" value={atlas.overview.total_lines.toLocaleString()} />
            </div>

            <div className="tab-bar" role="tablist">
              {TABS.map((t) => {
                const Icon = t.icon
                return (
                  <button
                    key={t.key}
                    type="button"
                    role="tab"
                    aria-selected={tab === t.key}
                    className={cn('tab-btn', tab === t.key && 'active')}
                    onClick={() => setTab(t.key)}
                  >
                    <Icon size={14} />
                    {t.label}
                  </button>
                )
              })}
            </div>

            {tab === 'flows' ? (
              <div className="flex flex-col gap-4">
                {atlas.flows.map((flow) => {
                  const meta = STATUS_META[flow.status]
                  return (
                    <div key={flow.id} className="card">
                      <div className="card-header">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <span className={cn('badge', meta.cls)}>{meta.label}</span>
                            <span className="card-title">{flow.name}</span>
                          </div>
                          <div className="card-description">{flow.summary}</div>
                        </div>
                        <span className="badge badge-neutral mono text-xs">{flow.trigger.name}</span>
                      </div>
                      <div className="card-body flex flex-col gap-3">
                        <ol className="atlas-steps">
                          {flow.steps.map((step, i) => (
                            <li key={i}>
                              <span className="mono text-xs">{step.component}</span>
                              <span className="text-muted"> — {step.action}</span>
                            </li>
                          ))}
                        </ol>
                        <div className="flex flex-wrap gap-1">
                          {flow.surfaces.map((surface) => (
                            <span key={surface} className="skill-tag">{surface}</span>
                          ))}
                        </div>
                        {flow.verification && flow.verification.length > 0 ? (
                          <div className="text-xs text-muted">
                            検証: {flow.verification.join(' / ')}
                          </div>
                        ) : null}
                        {flow.known_issues && flow.known_issues.length > 0 ? (
                          <div className="atlas-issues">
                            <div className="text-xs font-semibold">既知の問題 ({flow.known_issues.length})</div>
                            {flow.known_issues.map((issue, i) => (
                              <div key={i} className="atlas-issue">
                                <span className={cn('badge text-xs', SEVERITY_CLS[issue.severity] ?? 'badge-neutral')}>
                                  {issue.severity}
                                </span>
                                <div className="min-w-0">
                                  <div className="text-sm">{issue.title}</div>
                                  {issue.file ? <div className="text-xs mono text-muted">{issue.file}</div> : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : null}

            {tab === 'graph' ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">モジュール依存グラフ</div>
                    <div className="card-description">{atlas.graph.file_count} モジュールを {atlas.graph.nodes.length} サブシステムに集約</div>
                  </div>
                </div>
                <div className="card-body">
                  <DependencyGraph graph={atlas.graph} />
                </div>
              </div>
            ) : null}

            {tab === 'cli' ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">CLI コマンド ({filteredCli.length})</div>
                    <div className="card-description">build_parser から実行時に抽出した pantheon サブコマンド</div>
                  </div>
                  <input
                    className="input"
                    placeholder="コマンドを検索"
                    value={cliFilter}
                    onChange={(e) => setCliFilter(e.target.value)}
                    aria-label="CLI コマンド検索"
                  />
                </div>
                <div className="card-body">
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>コマンド</th>
                          <th>説明</th>
                          <th>引数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredCli.map((cmd) => (
                          <tr key={cmd.command}>
                            <td className="mono text-sm">{cmd.command}</td>
                            <td className="text-muted">{cmd.help || '—'}</td>
                            <td>
                              <div className="flex flex-wrap gap-1">
                                {cmd.args.length === 0 ? <span className="text-xs text-muted">—</span> : null}
                                {cmd.args.map((arg) => (
                                  <span key={arg.name} className={cn('badge text-xs', arg.required ? 'badge-blue' : 'badge-neutral')}>
                                    {arg.name}
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            {tab === 'api' ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">API ルート ({filteredApi.length})</div>
                    <div className="card-description">FastAPI app から実行時に抽出した REST / WebSocket エンドポイント</div>
                  </div>
                  <input
                    className="input"
                    placeholder="パスを検索"
                    value={apiFilter}
                    onChange={(e) => setApiFilter(e.target.value)}
                    aria-label="API ルート検索"
                  />
                </div>
                <div className="card-body">
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>メソッド</th>
                          <th>パス</th>
                          <th>種別</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredApi.map((route) => (
                          <tr key={`${route.kind}-${route.path}-${route.methods.join(',')}`}>
                            <td>
                              <div className="flex flex-wrap gap-1">
                                {route.methods.map((m) => (
                                  <span key={m} className={cn('badge text-xs', methodBadge(m))}>{m}</span>
                                ))}
                              </div>
                            </td>
                            <td className="mono text-sm">{route.path}</td>
                            <td>
                              <span className={cn('badge text-xs', route.kind === 'websocket' ? 'badge-blue' : 'badge-neutral')}>
                                {route.kind}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            {tab === 'subsystems' ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">サブシステム在庫 ({atlas.subsystems.length})</div>
                    <div className="card-description">トップレベルの責務領域・ファイル数・行数</div>
                  </div>
                </div>
                <div className="card-body">
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>サブシステム</th>
                          <th>役割</th>
                          <th>ファイル</th>
                          <th>行数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...atlas.subsystems].sort((a, b) => b.lines - a.lines).map((sub) => (
                          <tr key={sub.id}>
                            <td className="font-semibold">{sub.label}</td>
                            <td className="text-muted">{sub.purpose}</td>
                            <td className="mono text-sm">{sub.files}</td>
                            <td className="mono text-sm">{sub.lines.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            <div className="text-xs text-muted">
              生成時刻: {new Date(atlas.generated_at).toLocaleString()}
            </div>
          </>
        ) : null}
      </div>
    </>
  )
}
