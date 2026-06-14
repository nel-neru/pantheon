import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  GitBranch,
  Map as MapIcon,
  Network,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { cn, formatDateTime, formatNumber } from '@/lib/utils'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { Tabs } from '@/components/Tabs'

// ─── Domain types ─────────────────────────────────────────────────────────────

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
type StatusFilter = FlowStatus | 'all'
type SortKey = 'lines' | 'files' | 'label'
type SortDir = 'asc' | 'desc'

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_META: Record<FlowStatus, { label: string; cls: string }> = {
  solid: { label: '安定', cls: 'badge-green' },
  partial: { label: '一部課題', cls: 'badge-yellow' },
  fragile: { label: '要注意', cls: 'badge-red' },
  unknown: { label: '不明', cls: 'badge-neutral' },
}

const SEVERITY_LABEL: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

const SEVERITY_CLS: Record<string, string> = {
  high: 'badge-red',
  medium: 'badge-yellow',
  low: 'badge-neutral',
}

const SURFACE_CLS: Record<string, string> = {
  cli: 'badge-neutral',
  api: 'badge-blue',
  ui: 'badge-green',
}

const TRIGGER_LABEL: Record<string, string> = {
  cli: 'CLI',
  api: 'API',
  ui: 'UI',
  event: 'イベント',
}

function methodBadge(method: string): string {
  if (method === 'GET') return 'badge-green'
  if (method === 'POST') return 'badge-blue'
  if (method === 'PUT' || method === 'PATCH') return 'badge-yellow'
  if (method === 'DELETE') return 'badge-red'
  return 'badge-neutral'
}

function surfaceBadgeCls(surface: string): string {
  const key = surface.toLowerCase()
  if (key.startsWith('pantheon') || key === 'cli') return SURFACE_CLS.cli
  if (key.includes('page') || key.includes('ui')) return SURFACE_CLS.ui
  if (key.startsWith('/') || key === 'api') return SURFACE_CLS.api
  return 'badge-neutral'
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  onClick,
}: {
  label: string
  value: string | number
  onClick?: () => void
}) {
  if (onClick) {
    return (
      <button
        type="button"
        className="card text-left cursor-pointer hover:ring-1 hover:ring-blue-400 focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:outline-none"
        onClick={onClick}
      >
        <div className="card-body flex flex-col gap-1">
          <div className="text-2xl font-semibold mono">{value}</div>
          <div className="text-xs text-muted">{label}</div>
        </div>
      </button>
    )
  }
  return (
    <div className="card">
      <div className="card-body flex flex-col gap-1">
        <div className="text-2xl font-semibold mono">{value}</div>
        <div className="text-xs text-muted">{label}</div>
      </div>
    </div>
  )
}

// ─── Dependency Graph ──────────────────────────────────────────────────────────

function DependencyGraph({ graph }: { graph: AtlasModel['graph'] }) {
  const [focused, setFocused] = useState<string | null>(null)
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

  // Adjacency list for text alternative
  const adjacency = useMemo(() => {
    const map = new Map<string, string[]>()
    nodes.forEach((n) => map.set(n.id, []))
    graph.edges.forEach((e) => {
      map.get(e.source)?.push(e.target)
    })
    return map
  }, [nodes, graph.edges])

  if (nodes.length === 0) {
    return (
      <div className="empty-state">
        <Network className="empty-state-icon" size={28} />
        <h3>グラフデータがありません</h3>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="text-sm text-muted">
        ノード = サブシステム（円の大きさ ∝ ファイル数）、線 = import 依存（太さ ∝ 依存数）。
        ノードをクリック/フォーカスすると関連のみ強調します。
      </div>
      {/* SVG: width 100% responsive, viewBox kept */}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="atlas-graph w-full"
        role="group"
        aria-label={`サブシステム依存グラフ（${nodes.length} ノード）`}
      >
        {/* edges */}
        {graph.edges.map((edge, i) => {
          const a = positions.get(edge.source)
          const b = positions.get(edge.target)
          if (!a || !b) return null
          const active = focused === null || focused === edge.source || focused === edge.target
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
        {/* nodes as focusable elements */}
        {nodes.map((node) => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const r = 12 + Math.sqrt(node.files / maxFiles) * 22
          const active = focused === null || focused === node.id
          const neighbors = adjacency.get(node.id) ?? []
          const neighborLabels = neighbors
            .map((nid) => nodes.find((n) => n.id === nid)?.label ?? nid)
            .join('、')
          const ariaDesc = neighbors.length > 0
            ? `${node.label}（${node.files} ファイル）→ ${neighborLabels}`
            : `${node.label}（${node.files} ファイル）`
          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={ariaDesc}
              aria-pressed={focused === node.id}
              className="atlas-graph-node focus-visible:outline-none"
              onClick={() => setFocused(focused === node.id ? null : node.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setFocused(focused === node.id ? null : node.id)
                }
              }}
              onFocus={() => setFocused(node.id)}
              onBlur={() => setFocused(null)}
              onMouseEnter={() => setFocused(node.id)}
              onMouseLeave={() => setFocused(null)}
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={r}
                fillOpacity={active ? 0.85 : 0.25}
                className={focused === node.id ? 'stroke-blue-400' : ''}
                strokeWidth={focused === node.id ? 2 : 0}
              />
              <text x={pos.x} y={pos.y - r - 6} textAnchor="middle" className="atlas-graph-label" aria-hidden="true">
                {node.label}
              </text>
              <text x={pos.x} y={pos.y + 4} textAnchor="middle" className="atlas-graph-count" aria-hidden="true">
                {node.files}
              </text>
            </g>
          )
        })}
      </svg>
      {/* Text alternative: adjacency list */}
      <details className="text-xs text-muted">
        <summary className="cursor-pointer select-none">依存関係テキスト一覧</summary>
        <ul className="mt-2 flex flex-col gap-1 list-none">
          {nodes.map((node) => {
            const neighbors = adjacency.get(node.id) ?? []
            return (
              <li key={node.id}>
                <span className="font-semibold mono">{node.label}</span>
                {' '}
                <span className="text-muted">({node.files} ファイル)</span>
                {neighbors.length > 0 ? (
                  <>
                    {' → '}
                    {neighbors.map((nid) => nodes.find((n) => n.id === nid)?.label ?? nid).join('、')}
                  </>
                ) : null}
              </li>
            )
          })}
        </ul>
      </details>
    </div>
  )
}

// ─── FlowsPanel ───────────────────────────────────────────────────────────────

function FlowsPanel({
  flows,
  statusFilter,
  onStatusFilterChange,
}: {
  flows: Flow[]
  statusFilter: StatusFilter
  onStatusFilterChange: (s: StatusFilter) => void
}) {
  const filtered = useMemo(
    () => (statusFilter === 'all' ? flows : flows.filter((f) => f.status === statusFilter)),
    [flows, statusFilter],
  )

  const STATUS_FILTER_TABS = useMemo(() => {
    const all = flows.length
    const solid = flows.filter((f) => f.status === 'solid').length
    const partial = flows.filter((f) => f.status === 'partial').length
    const fragile = flows.filter((f) => f.status === 'fragile').length
    return [
      { value: 'all' as StatusFilter, label: 'すべて', count: all },
      { value: 'solid' as StatusFilter, label: '安定', count: solid },
      { value: 'partial' as StatusFilter, label: '一部課題', count: partial },
      { value: 'fragile' as StatusFilter, label: '要注意', count: fragile },
    ]
  }, [flows])

  return (
    <div className="flex flex-col gap-4">
      <Tabs
        tabs={STATUS_FILTER_TABS}
        value={statusFilter}
        onChange={onStatusFilterChange}
        ariaLabel="フロー状態フィルタ"
      />
      {filtered.length === 0 ? (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <GitBranch className="empty-state-icon" size={28} />
              <h3>フローがありません</h3>
            </div>
          </div>
        </div>
      ) : null}
      {filtered.map((flow) => {
        const meta = STATUS_META[flow.status]
        const triggerLabel = TRIGGER_LABEL[flow.trigger.kind] ?? flow.trigger.kind.toUpperCase()
        return (
          <div key={flow.id} className="card">
            <div className="card-header">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={cn('badge', meta.cls)}>{meta.label}</span>
                  <span className="card-title">{flow.name}</span>
                </div>
                <div className="card-description">{flow.summary}</div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="badge badge-neutral text-xs">{triggerLabel}</span>
                <span className="badge badge-neutral mono text-xs">{flow.trigger.name}</span>
              </div>
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

              {/* Surface tags with label */}
              {flow.surfaces.length > 0 ? (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted">接点:</span>
                  {flow.surfaces.map((surface) => (
                    <span key={surface} className={cn('badge text-xs', surfaceBadgeCls(surface))}>
                      {surface}
                    </span>
                  ))}
                </div>
              ) : null}

              {/* Verification as tags */}
              {flow.verification && flow.verification.length > 0 ? (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted">検証:</span>
                  {flow.verification.map((v, i) => (
                    <span key={i} className="badge badge-neutral mono text-xs">{v}</span>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-muted">検証なし（fragile 判定の根拠が不明）</div>
              )}

              {/* Known issues with detail */}
              {flow.known_issues && flow.known_issues.length > 0 ? (
                <div className="atlas-issues">
                  <div className="text-xs font-semibold">既知の問題 ({flow.known_issues.length})</div>
                  {flow.known_issues.map((issue, i) => (
                    <div key={i} className="atlas-issue">
                      <span className={cn('badge text-xs', SEVERITY_CLS[issue.severity] ?? 'badge-neutral')}>
                        {SEVERITY_LABEL[issue.severity] ?? issue.severity}
                      </span>
                      <div className="min-w-0 flex flex-col gap-1">
                        <div className="text-sm">{issue.title}</div>
                        {issue.file ? <div className="text-xs mono text-muted">{issue.file}</div> : null}
                        {issue.detail ? (
                          <details className="text-xs text-muted">
                            <summary className="cursor-pointer select-none">詳細</summary>
                            <p className="mt-1">{issue.detail}</p>
                          </details>
                        ) : null}
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
  )
}

// ─── CliPanel ─────────────────────────────────────────────────────────────────

function CliPanel({
  cli,
  filter,
  onFilterChange,
  totalCount,
}: {
  cli: CliCommand[]
  filter: string
  onFilterChange: (v: string) => void
  totalCount: number
}) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">CLI コマンド ({cli.length} / 全{totalCount}件)</div>
          <div className="card-description">build_parser から実行時に抽出した pantheon サブコマンド（handler 有り）</div>
        </div>
        <div className="flex items-center gap-2">
          <input
            className="input"
            placeholder="コマンドを検索"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            aria-label="CLI コマンド検索"
          />
          {filter ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onFilterChange('')}
              aria-label="検索をクリア"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>
      <div className="card-body">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>コマンド</th>
                <th>説明</th>
                <th>
                  引数
                  <span className="text-xs text-muted font-normal ml-2">
                    （<span className="badge badge-blue text-xs">必須</span> / <span className="badge badge-neutral text-xs">任意</span>）
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {cli.length === 0 ? (
                <tr>
                  <td colSpan={3} className="text-center text-muted py-4">
                    該当コマンドなし
                  </td>
                </tr>
              ) : null}
              {cli.map((cmd) => (
                <tr key={cmd.command}>
                  <td className="mono text-sm">{cmd.command}</td>
                  <td className="text-muted">{cmd.help || '—'}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {cmd.args.length === 0 ? <span className="text-xs text-muted">—</span> : null}
                      {cmd.args.map((arg) => (
                        <span
                          key={arg.name}
                          className={cn('badge text-xs', arg.required ? 'badge-blue' : 'badge-neutral')}
                          title={arg.required ? '必須' : '任意'}
                        >
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
  )
}

// ─── ApiPanel ─────────────────────────────────────────────────────────────────

function ApiPanel({
  routes,
  filter,
  onFilterChange,
  totalCount,
}: {
  routes: ApiRoute[]
  filter: string
  onFilterChange: (v: string) => void
  totalCount: number
}) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">API ルート ({routes.length} / 全{totalCount}件)</div>
          <div className="card-description">FastAPI app から実行時に抽出した REST / WebSocket エンドポイント</div>
        </div>
        <div className="flex items-center gap-2">
          <input
            className="input"
            placeholder="パスを検索"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            aria-label="API ルート検索"
          />
          {filter ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onFilterChange('')}
              aria-label="検索をクリア"
            >
              ×
            </button>
          ) : null}
        </div>
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
              {routes.length === 0 ? (
                <tr>
                  <td colSpan={3} className="text-center text-muted py-4">
                    該当ルートなし
                  </td>
                </tr>
              ) : null}
              {routes.map((route) => (
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
                    <span className={cn(
                      'badge text-xs',
                      route.kind === 'websocket' ? 'badge-blue' :
                      route.kind === 'error' ? 'badge-red' :
                      'badge-neutral'
                    )}>
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
  )
}

// ─── SubsystemsPanel ──────────────────────────────────────────────────────────

function SubsystemsPanel({ subsystems }: { subsystems: Subsystem[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('lines')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const sorted = useMemo(() => {
    return [...subsystems].sort((a, b) => {
      let diff = 0
      if (sortKey === 'lines') diff = a.lines - b.lines
      else if (sortKey === 'files') diff = a.files - b.files
      else diff = a.label.localeCompare(b.label)
      return sortDir === 'desc' ? -diff : diff
    })
  }, [subsystems, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return null
    return sortDir === 'desc' ? ' ↓' : ' ↑'
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">サブシステム在庫 ({subsystems.length})</div>
          <div className="card-description">トップレベルの責務領域・ファイル数・行数（列ヘッダクリックでソート）</div>
        </div>
      </div>
      <div className="card-body">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <button
                    type="button"
                    className="text-left font-semibold"
                    onClick={() => handleSort('label')}
                    aria-sort={sortKey === 'label' ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
                  >
                    サブシステム{sortIcon('label')}
                  </button>
                </th>
                <th>役割</th>
                <th>
                  <button
                    type="button"
                    className="text-left font-semibold"
                    onClick={() => handleSort('files')}
                    aria-sort={sortKey === 'files' ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
                  >
                    ファイル{sortIcon('files')}
                  </button>
                </th>
                <th>
                  <button
                    type="button"
                    className="text-left font-semibold"
                    onClick={() => handleSort('lines')}
                    aria-sort={sortKey === 'lines' ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
                  >
                    行数{sortIcon('lines')}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((sub) => (
                <Fragment key={sub.id}>
                  <tr
                    className={sub.paths && sub.paths.length > 0 ? 'cursor-pointer hover:bg-muted/20' : undefined}
                    onClick={
                      sub.paths && sub.paths.length > 0
                        ? () => setExpandedId(expandedId === sub.id ? null : sub.id)
                        : undefined
                    }
                  >
                    <td className="font-semibold">
                      {sub.label}
                      {sub.paths && sub.paths.length > 0 ? (
                        <span className="text-xs text-muted ml-1">{expandedId === sub.id ? '▲' : '▼'}</span>
                      ) : null}
                    </td>
                    <td className="text-muted">{sub.purpose}</td>
                    <td className="mono text-sm">{sub.files}</td>
                    <td className="mono text-sm">{formatNumber(sub.lines)}</td>
                  </tr>
                  {expandedId === sub.id && sub.paths && sub.paths.length > 0 ? (
                    <tr>
                      <td colSpan={4} className="bg-muted/10 py-2 px-4">
                        <div className="text-xs text-muted font-semibold mb-1">対象パス:</div>
                        <div className="flex flex-wrap gap-1">
                          {sub.paths.map((p) => (
                            <span key={p} className="badge badge-neutral mono text-xs">{p}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function AtlasPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const tabParam = (searchParams.get('tab') ?? 'flows') as TabKey
  const validTabs: TabKey[] = ['flows', 'graph', 'cli', 'api', 'subsystems']
  const tab: TabKey = validTabs.includes(tabParam) ? tabParam : 'flows'

  const [atlas, setAtlas] = useState<AtlasModel | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cliFilter, setCliFilter] = useState('')
  const [apiFilter, setApiFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const setTab = (t: TabKey) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', t)
    setSearchParams(next, { replace: true })
  }

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    else setRefreshing(true)
    try {
      const data = await api<AtlasModel>('GET', '/api/atlas')
      setAtlas(data)
      setError(null)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Atlas の読み込みに失敗しました。'
      setError(message)
      if (quiet) {
        // quiet re-fetch: only toast, keep existing data
        toast.error(message)
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

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

  // Generated_at freshness
  const generatedAtDisplay = atlas ? formatDateTime(atlas.generated_at) : null
  const generatedAtDate = atlas ? new Date(atlas.generated_at) : null
  const isStale = generatedAtDate && !Number.isNaN(generatedAtDate.getTime())
    ? Date.now() - generatedAtDate.getTime() > 3 * 60 * 60 * 1000 // > 3h
    : false

  const TAB_ITEMS = [
    { value: 'flows' as TabKey, label: '使用フロー' },
    { value: 'graph' as TabKey, label: '依存グラフ' },
    { value: 'cli' as TabKey, label: 'CLI' },
    { value: 'api' as TabKey, label: 'API' },
    { value: 'subsystems' as TabKey, label: 'サブシステム' },
  ]

  const goToFlowsWithFilter = (status: StatusFilter) => {
    setStatusFilter(status)
    setTab('flows')
  }

  // Status badge classes: only show red for fragile when count > 0
  const fragileCount = statusCounts.fragile
  const fragileBadgeCls = fragileCount > 0 ? 'badge badge-red cursor-pointer' : 'badge badge-neutral cursor-pointer'

  const headerActions = atlas ? (
    <>
      <button
        type="button"
        className="badge badge-green cursor-pointer"
        onClick={() => goToFlowsWithFilter('solid')}
        title="安定フローを表示"
      >
        安定 {statusCounts.solid}
      </button>
      <button
        type="button"
        className="badge badge-yellow cursor-pointer"
        onClick={() => goToFlowsWithFilter('partial')}
        title="一部課題フローを表示"
      >
        一部課題 {statusCounts.partial}
      </button>
      <button
        type="button"
        className={fragileBadgeCls}
        onClick={() => goToFlowsWithFilter('fragile')}
        title="要注意フローを表示"
      >
        要注意 {fragileCount}
      </button>
      {generatedAtDisplay ? (
        <span className={cn('text-xs', isStale ? 'text-red-500' : 'text-muted')} title={generatedAtDisplay}>
          {isStale ? '古い情報（' : '生成: '}{generatedAtDisplay}{isStale ? '）' : ''}
        </span>
      ) : null}
      <RefreshButton onClick={() => void load(true)} busy={refreshing} />
    </>
  ) : (
    <RefreshButton onClick={() => void load(false)} busy={loading || refreshing} />
  )

  return (
    <>
      <PageHeader
        title={
          <div className="flex items-center gap-2">
            <MapIcon size={18} />
            Atlas — リポジトリ俯瞰
          </div>
        }
        actions={headerActions}
      />

      <div className="page-content flex flex-col gap-5">
        <AsyncBoundary
          loading={loading}
          error={!atlas ? error : null}
          onRetry={() => void load()}
          loadingText="リポジトリを解析中…"
          errorTitle="Atlas の読み込みに失敗しました"
        >
          {atlas ? (
            <>
              {/* StatCards — clickable, navigate to relevant tab */}
              <div className="grid-4">
                <StatCard
                  label="使用フロー"
                  value={atlas.overview.flows}
                  onClick={() => setTab('flows')}
                />
                <StatCard
                  label={`CLI コマンド（うち実行可能 ${atlas.cli.filter((c) => c.handler).length}）`}
                  value={atlas.overview.cli_commands}
                  onClick={() => setTab('cli')}
                />
                <StatCard
                  label={`API ルート（REST + WS ${atlas.overview.websockets}）`}
                  value={formatNumber(atlas.overview.api_routes + atlas.overview.websockets)}
                  onClick={() => setTab('api')}
                />
                <StatCard
                  label="UI ページ"
                  value={atlas.overview.pages}
                />
                <StatCard
                  label="サブシステム"
                  value={atlas.overview.subsystems}
                  onClick={() => setTab('subsystems')}
                />
                <StatCard
                  label="モジュール（依存グラフ）"
                  value={atlas.overview.modules}
                  onClick={() => setTab('graph')}
                />
                <StatCard
                  label="総ファイル数"
                  value={formatNumber(atlas.overview.total_files)}
                />
                <StatCard
                  label="総行数"
                  value={formatNumber(atlas.overview.total_lines)}
                />
              </div>

              <Tabs
                tabs={TAB_ITEMS}
                value={tab}
                onChange={setTab}
                ariaLabel="Atlas タブ"
              />

              <div role="tabpanel" aria-label={TAB_ITEMS.find((t) => t.value === tab)?.label}>
                {tab === 'flows' ? (
                  <FlowsPanel
                    flows={atlas.flows}
                    statusFilter={statusFilter}
                    onStatusFilterChange={setStatusFilter}
                  />
                ) : null}

                {tab === 'graph' ? (
                  <div className="card">
                    <div className="card-header">
                      <div>
                        <div className="card-title">モジュール依存グラフ</div>
                        <div className="card-description">
                          {formatNumber(atlas.graph.file_count)} モジュールを {atlas.graph.nodes.length} サブシステムに集約
                        </div>
                      </div>
                    </div>
                    <div className="card-body">
                      <DependencyGraph graph={atlas.graph} />
                    </div>
                  </div>
                ) : null}

                {tab === 'cli' ? (
                  <CliPanel
                    cli={filteredCli}
                    filter={cliFilter}
                    onFilterChange={setCliFilter}
                    totalCount={atlas.cli.filter((c) => c.handler).length}
                  />
                ) : null}

                {tab === 'api' ? (
                  <ApiPanel
                    routes={filteredApi}
                    filter={apiFilter}
                    onFilterChange={setApiFilter}
                    totalCount={atlas.api.length}
                  />
                ) : null}

                {tab === 'subsystems' ? (
                  <SubsystemsPanel subsystems={atlas.subsystems} />
                ) : null}
              </div>
            </>
          ) : null}
        </AsyncBoundary>
      </div>
    </>
  )
}
