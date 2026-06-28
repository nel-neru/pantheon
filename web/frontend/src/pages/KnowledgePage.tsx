import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertTriangle,
  BookMarked,
  ExternalLink,
  Info,
  Minus,
  Network,
  Plus,
  RotateCcw,
  Save,
  X,
} from 'lucide-react'
import { toast } from 'sonner'

import {
  api,
  editVaultNote,
  getVaultGraph,
  syncVault,
} from '@/lib/api'
import type {
  VaultGraph,
  VaultGraphEdge,
  VaultGraphNode,
  VaultNoteDetail,
  VaultNotesResponse,
  VaultNoteSummary,
  VaultWikiLink,
} from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
import { Tabs } from '@/components/Tabs'
import { cn, formatDateTime } from '@/lib/utils'

// ─── Wikilink preprocessing ───────────────────────────────────────────────────

/**
 * Replace [[type:target|alias]] (or [[target|alias]]) wikilink patterns in
 * markdown body with [alias-or-target](#wikilink:<node_id>) so react-markdown
 * can delegate them to a custom <a> renderer.
 */
function preprocessWikilinks(body: string): string {
  // Matches [[type:target|alias]], [[target|alias]], [[type:target]], [[target]]
  return body.replace(/\[\[([^\]]+)\]\]/g, (_, inner: string) => {
    const [ref, ...aliasParts] = inner.split('|')
    const alias = aliasParts.join('|').trim() || ref.trim()
    // node_id = the full ref (may include "type:target")
    const nodeId = ref.trim()
    return `[${alias}](#wikilink:${encodeURIComponent(nodeId)})`
  })
}

// ─── Type / canonical badge helpers ──────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  insight: 'インサイト',
  playbook: 'プレイブック',
  outcome: 'アウトカム',
}

const TYPE_BADGE: Record<string, string> = {
  insight: 'badge-blue',
  playbook: 'badge-green',
  outcome: 'badge-yellow',
}

function typeBadgeCls(type: string): string {
  return TYPE_BADGE[type] ?? 'badge-neutral'
}

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type
}

// ─── Graph color map by pantheon_type (group) ────────────────────────────────

const GROUP_COLOR: Record<string, string> = {
  insight: '#60a5fa',    // blue-400
  playbook: '#4ade80',   // green-400
  outcome: '#facc15',    // yellow-400
  pattern: '#a78bfa',    // violet-400
  org: '#fb923c',        // orange-400
  handoff: '#f472b6',    // pink-400
}

function groupColor(group: string): string {
  return GROUP_COLOR[group] ?? '#94a3b8' // slate-400 fallback
}

// ─── NoteList pane ────────────────────────────────────────────────────────────

function NoteList({
  notes,
  selected,
  onSelect,
}: {
  notes: VaultNoteSummary[]
  selected: string | null
  onSelect: (path: string) => void
}) {
  // Group by subdir
  const groups = useMemo(() => {
    const map = new Map<string, VaultNoteSummary[]>()
    for (const note of notes) {
      const key = note.subdir || 'その他'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(note)
    }
    return map
  }, [notes])

  if (notes.length === 0) {
    return (
      <div className="text-muted text-sm px-2 py-4">ノートがありません。</div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {Array.from(groups.entries()).map(([subdir, groupNotes]) => (
        <div key={subdir}>
          <div className="flex items-center gap-2 px-2 mb-1">
            <span className="text-xs font-semibold text-muted uppercase tracking-wide">
              {subdir}
            </span>
            <span className="badge badge-neutral text-xs">{groupNotes.length}</span>
          </div>
          <div className="flex flex-col gap-1">
            {groupNotes.map((note) => (
              <button
                key={note.path}
                type="button"
                className={cn(
                  'text-left w-full px-3 py-2 rounded flex items-start gap-2 transition-colors',
                  selected === note.path
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'hover:bg-white/5 text-inherit',
                )}
                onClick={() => onSelect(note.path)}
                aria-label={note.title}
                aria-pressed={selected === note.path}
              >
                <span className={cn('badge text-xs mt-0.5 shrink-0', typeBadgeCls(note.type))}>
                  {typeLabel(note.type)}
                </span>
                <span className="text-sm leading-snug break-all">{note.title}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── WikiLink chip ─────────────────────────────────────────────────────────────

function WikiLinkChip({
  link,
  onNavigate,
}: {
  link: VaultWikiLink
  onNavigate: (path: string) => void
}) {
  if (link.resolved && link.resolved_path) {
    return (
      <button
        type="button"
        className="badge badge-blue text-xs cursor-pointer hover:opacity-80"
        onClick={() => onNavigate(link.resolved_path)}
        title={`${link.type}:${link.target}`}
      >
        {link.alias || link.target}
      </button>
    )
  }
  return (
    <span className="badge badge-neutral text-xs opacity-50" title="未解決リンク">
      {link.alias || link.target}
    </span>
  )
}

// ─── NoteDetail pane ──────────────────────────────────────────────────────────

function NoteDetail({
  detail,
  onNavigate,
  onReload,
}: {
  detail: VaultNoteDetail
  onNavigate: (path: string) => void
  onReload: (path: string) => void
}) {
  // Strip the auto-generated Related block before exposing to editor
  const editableContent = useMemo(
    () => detail.body.split('<!-- pantheon:related')[0].trimEnd(),
    [detail.body],
  )

  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(editableContent)
  const [saving, setSaving] = useState(false)

  // Reset edit state when a different note is opened
  const prevPath = useRef(detail.path)
  if (prevPath.current !== detail.path) {
    prevPath.current = detail.path
    if (editMode) {
      setEditMode(false)
    }
    setEditText(detail.body.split('<!-- pantheon:related')[0].trimEnd())
  }

  const handleEdit = useCallback(() => {
    setEditText(editableContent)
    setEditMode(true)
  }, [editableContent])

  const handleCancel = useCallback(() => {
    setEditMode(false)
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await editVaultNote(detail.path, editText)
      toast.success('保存しました。')
      setEditMode(false)
      onReload(detail.path)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存に失敗しました。')
    } finally {
      setSaving(false)
    }
  }, [detail.path, editText, onReload])

  // Build a lookup: encoded nodeId → resolved_path (for custom link renderer)
  const wikilinkMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const wl of detail.wikilinks) {
      if (wl.resolved && wl.resolved_path) {
        m.set(encodeURIComponent(wl.node_id), wl.resolved_path)
      }
    }
    return m
  }, [detail.wikilinks])

  const processedBody = useMemo(() => preprocessWikilinks(detail.body), [detail.body])

  return (
    <div className="flex flex-col gap-4">
      {/* Title + badges + edit button */}
      <div className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-2">
          <h1 className="text-xl font-semibold leading-tight">{detail.title}</h1>
          {detail.canonical === 'vault' && !editMode ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm shrink-0"
              onClick={handleEdit}
              aria-label="編集"
            >
              編集
            </button>
          ) : null}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn('badge', typeBadgeCls(detail.type))}>
            {typeLabel(detail.type)}
          </span>
          {detail.canonical === 'json' ? (
            <span className="badge badge-yellow" title="JSONデータから生成された読み取り専用ミラー">
              読み取り専用ミラー
            </span>
          ) : (
            <span className="badge badge-neutral">{detail.canonical}</span>
          )}
        </div>
      </div>

      {/* Conflict warning */}
      {detail.has_conflict ? (
        <div className="flex items-start gap-2 rounded border border-yellow-500/40 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-300">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          <span>
            このノートはコンフリクト状態です。Obsidian アプリで確認して解決してください。
          </span>
        </div>
      ) : null}

      {/* Tags */}
      {detail.tags.length > 0 ? (
        <div className="flex items-center gap-1 flex-wrap">
          {detail.tags.map((tag) => (
            <span key={tag} className="badge badge-neutral text-xs">#{tag}</span>
          ))}
        </div>
      ) : null}

      {/* Edit mode: textarea */}
      {editMode ? (
        <div className="flex flex-col gap-2">
          <textarea
            className="input font-mono text-sm min-h-64 resize-y w-full"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            aria-label="ノート編集エリア"
            disabled={saving}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-primary btn-sm flex items-center gap-1"
              onClick={() => void handleSave()}
              disabled={saving}
              aria-label="保存"
            >
              <Save size={13} />
              {saving ? '保存中…' : '保存'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm flex items-center gap-1"
              onClick={handleCancel}
              disabled={saving}
              aria-label="キャンセル"
            >
              <X size={13} />
              キャンセル
            </button>
          </div>
        </div>
      ) : (
        /* Read mode: Markdown body */
        <div className="prose-vault">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a({ href, children, ...props }) {
                if (href && href.startsWith('#wikilink:')) {
                  const encoded = href.slice('#wikilink:'.length)
                  const resolvedPath = wikilinkMap.get(encoded)
                  if (resolvedPath) {
                    return (
                      <button
                        type="button"
                        className="badge badge-blue text-xs cursor-pointer hover:opacity-80 align-baseline"
                        onClick={() => onNavigate(resolvedPath)}
                      >
                        {children}
                      </button>
                    )
                  }
                  // Unresolved wikilink — muted, not clickable
                  return (
                    <span className="badge badge-neutral text-xs opacity-50 align-baseline">
                      {children}
                    </span>
                  )
                }
                // Regular external link
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-400 underline"
                    {...props}
                  >
                    {children}
                    <ExternalLink size={11} />
                  </a>
                )
              },
            }}
          >
            {processedBody}
          </ReactMarkdown>
        </div>
      )}

      {/* Wikilinks section */}
      <div className="border-t border-white/10 pt-3 flex flex-col gap-3">
        <div>
          <div className="text-xs font-semibold text-muted mb-1">リンク</div>
          {detail.wikilinks.length === 0 ? (
            <span className="text-xs text-muted">（リンクなし）</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {detail.wikilinks.map((wl, i) => (
                <WikiLinkChip key={i} link={wl} onNavigate={onNavigate} />
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-semibold text-muted mb-1">バックリンク</div>
          {detail.backlinks.length === 0 ? (
            <span className="text-xs text-muted">（リンクなし）</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {detail.backlinks.map((bl) => (
                <button
                  key={bl.path}
                  type="button"
                  className="badge badge-blue text-xs cursor-pointer hover:opacity-80"
                  onClick={() => onNavigate(bl.path)}
                  title={bl.path}
                >
                  {bl.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Footer: sync time */}
      <div className="text-xs text-muted pt-1">
        最終同期: {formatDateTime(detail.synced_at)}
      </div>
    </div>
  )
}

// ─── Vault Graph ──────────────────────────────────────────────────────────────

const ZOOM_LEVELS: readonly number[] = [1, 0.75, 0.5, 0.35]
const ZOOM_LABELS: readonly string[] = ['100%', '133%', '200%', '286%']
const ZOOM_DEFAULT = 0

function VaultGraphView({
  graph,
  onOpenNote,
}: {
  graph: VaultGraph
  onOpenNote: (path: string) => void
}) {
  const [focused, setFocused] = useState<string | null>(null)
  const [zoomIdx, setZoomIdx] = useState(ZOOM_DEFAULT)
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const isDragging = useRef(false)
  const dragStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const BASE_WIDTH = 760
  const BASE_HEIGHT = 520
  const cx = BASE_WIDTH / 2
  const cy = BASE_HEIGHT / 2
  const radius = 200
  const nodes = graph.nodes
  const maxWeight = Math.max(1, ...graph.edges.map((e) => e.weight))

  const scale = ZOOM_LEVELS[zoomIdx] ?? 1
  const zoomLabel = ZOOM_LABELS[zoomIdx] ?? '100%'
  const vbW = BASE_WIDTH * scale
  const vbH = BASE_HEIGHT * scale
  const maxPan = ((1 - scale) / 2) * BASE_WIDTH + 100
  const clampedPan = {
    x: Math.max(-maxPan, Math.min(maxPan, pan.x)),
    y: Math.max(-maxPan, Math.min(maxPan, pan.y)),
  }
  const vbX = (BASE_WIDTH - vbW) / 2 + clampedPan.x
  const vbY = (BASE_HEIGHT - vbH) / 2 + clampedPan.y
  const viewBox = `${vbX} ${vbY} ${vbW} ${vbH}`

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>()
    nodes.forEach((node, index) => {
      const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2
      map.set(node.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) })
    })
    return map
  }, [nodes, cx, cy])

  const zoomIn = useCallback(() => {
    setZoomIdx((z) => Math.min(z + 1, ZOOM_LEVELS.length - 1))
  }, [])
  const zoomOut = useCallback(() => {
    setZoomIdx((z) => Math.max(z - 1, 0))
    setPan((p) => (zoomIdx <= 1 ? { x: 0, y: 0 } : p))
  }, [zoomIdx])
  const zoomReset = useCallback(() => {
    setZoomIdx(ZOOM_DEFAULT)
    setPan({ x: 0, y: 0 })
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as Element).closest('[role="button"]')) return
    isDragging.current = true
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }
    e.preventDefault()
  }, [pan])

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging.current || !dragStart.current || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const scaleX = vbW / rect.width
    const scaleY = vbH / rect.height
    const dx = (e.clientX - dragStart.current.mx) * scaleX
    const dy = (e.clientY - dragStart.current.my) * scaleY
    setPan({ x: dragStart.current.px - dx, y: dragStart.current.py - dy })
  }, [vbW, vbH])

  const handleMouseUp = useCallback(() => {
    isDragging.current = false
    dragStart.current = null
  }, [])

  if (nodes.length === 0) {
    return (
      <div className="empty-state">
        <Network className="empty-state-icon" size={28} />
        <h3>グラフデータがありません</h3>
        <p>
          ターミナルで{' '}
          <code className="mono text-xs bg-white/10 px-1 py-0.5 rounded">
            pantheon vault export
          </code>{' '}
          を実行するとグラフが生成されます。
        </p>
      </div>
    )
  }

  // Unique groups present in the graph for the legend
  const groups = Array.from(new Set(nodes.map((n) => n.group))).sort()

  return (
    <div className="flex flex-col gap-4">
      {/* Counts bar */}
      <div className="flex items-center gap-4 flex-wrap text-xs text-muted">
        <span>ノート: <strong className="text-inherit">{graph.counts.notes}</strong></span>
        <span>エッジ: <strong className="text-inherit">{graph.counts.edges}</strong></span>
        <span>解決済みリンク: <strong className="text-inherit">{graph.counts.resolved_links}</strong></span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <span className="text-muted">種別:</span>
        {groups.map((g) => (
          <span key={g} className="flex items-center gap-1">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ background: groupColor(g) }}
              aria-hidden="true"
            />
            <span>{g}</span>
          </span>
        ))}
        <span className="flex items-center gap-1 opacity-50">
          <span className="inline-block w-3 h-3 rounded-full border border-dashed border-current" aria-hidden="true" />
          <span>未解決ノード</span>
        </span>
      </div>

      {/* Zoom controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-xs text-muted">
          ノードをクリックすると detail を開きます。ドラッグでパン。
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="ズーム操作">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={zoomOut}
            disabled={zoomIdx === 0}
            aria-label="縮小"
          >
            <Minus size={14} />
          </button>
          <span className="text-xs text-muted mono w-10 text-center" aria-live="polite">
            {zoomLabel}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={zoomIn}
            disabled={zoomIdx === ZOOM_LEVELS.length - 1}
            aria-label="拡大"
          >
            <Plus size={14} />
          </button>
          {(zoomIdx !== ZOOM_DEFAULT || pan.x !== 0 || pan.y !== 0) ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={zoomReset}
              aria-label="ズームをリセット"
            >
              <RotateCcw size={14} />
            </button>
          ) : null}
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={viewBox}
        className={cn('w-full', zoomIdx > 0 ? 'cursor-grab active:cursor-grabbing' : '')}
        style={{ minHeight: 320, background: 'transparent' }}
        role="group"
        aria-label={`Vault グラフ（${nodes.length} ノード）`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* edges */}
        {(graph.edges as VaultGraphEdge[]).map((edge, i) => {
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
              strokeWidth={1 + (edge.weight / maxWeight) * 4}
              strokeOpacity={active ? 0.4 : 0.05}
            />
          )
        })}
        {/* nodes */}
        {(nodes as VaultGraphNode[]).map((node) => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const isUnresolved = node.files === 0
          const isClickable = node.path !== ''
          const active = focused === null || focused === node.id
          const color = groupColor(node.group)
          const r = isUnresolved ? 8 : 14
          return (
            <g
              key={node.id}
              tabIndex={isClickable ? 0 : undefined}
              role={isClickable ? 'button' : undefined}
              aria-label={isClickable ? `${node.label}（クリックして開く）` : `${node.label}（未解決）`}
              className={isClickable ? 'cursor-pointer focus-visible:outline-none' : 'cursor-default'}
              onClick={() => {
                if (isClickable) {
                  onOpenNote(node.path)
                }
              }}
              onKeyDown={(e) => {
                if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onOpenNote(node.path)
                }
              }}
              onMouseEnter={() => setFocused(node.id)}
              onMouseLeave={() => setFocused(null)}
              onFocus={() => setFocused(node.id)}
              onBlur={() => setFocused(null)}
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={r}
                fill={color}
                fillOpacity={isUnresolved ? 0.2 : (active ? 0.85 : 0.3)}
                stroke={isUnresolved ? color : (focused === node.id ? '#93c5fd' : color)}
                strokeWidth={focused === node.id ? 2 : (isUnresolved ? 1 : 0)}
                strokeDasharray={isUnresolved ? '3 2' : undefined}
              />
              <text
                x={pos.x}
                y={pos.y - r - 5}
                textAnchor="middle"
                fontSize={10}
                fill="currentColor"
                fillOpacity={active ? 0.9 : 0.3}
                aria-hidden="true"
              >
                {node.label.length > 14 ? node.label.slice(0, 12) + '…' : node.label}
              </text>
              {focused === node.id && isUnresolved ? (
                <title>未解決</title>
              ) : null}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ─── Graph tab wrapper (fetches data) ─────────────────────────────────────────

function GraphTab({ onOpenNote }: { onOpenNote: (path: string) => void }) {
  const [graph, setGraph] = useState<VaultGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void getVaultGraph()
      .then((data) => {
        if (!cancelled) {
          setGraph(data)
          setError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'グラフの読み込みに失敗しました。')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <AsyncBoundary
      loading={loading}
      error={error}
      onRetry={() => {
        setError(null)
        setLoading(true)
        void getVaultGraph()
          .then((data) => {
            setGraph(data)
            setError(null)
          })
          .catch((e) => {
            setError(e instanceof Error ? e.message : 'グラフの読み込みに失敗しました。')
          })
          .finally(() => setLoading(false))
      }}
      loadingText="グラフを読み込み中…"
      errorTitle="グラフの読み込みに失敗しました"
    >
      {graph ? (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Vault グラフ</div>
          </div>
          <div className="card-body">
            <VaultGraphView graph={graph} onOpenNote={onOpenNote} />
          </div>
        </div>
      ) : null}
    </AsyncBoundary>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type PageTab = 'browser' | 'graph'

export function KnowledgePage() {
  const [tab, setTab] = useState<PageTab>('browser')
  const [notes, setNotes] = useState<VaultNoteSummary[]>([])
  const [vaultDir, setVaultDir] = useState<string>('')
  const [vaultExists, setVaultExists] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [detail, setDetail] = useState<VaultNoteDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const loadNotes = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await api<VaultNotesResponse>('GET', '/api/vault/notes')
      setNotes(res.notes)
      setVaultDir(res.vault_dir)
      setVaultExists(res.exists)
      setError(null)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Vault ノートの読み込みに失敗しました。'
      setError(msg)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void loadNotes()
  }, [loadNotes])

  const loadDetail = useCallback(async (path: string) => {
    setSelectedPath(path)
    setDetailLoading(true)
    setDetailError(null)
    setDetail(null)
    try {
      const res = await api<VaultNoteDetail>('GET', `/api/vault/notes/${path}`)
      setDetail(res)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'ノートの読み込みに失敗しました。'
      setDetailError(msg)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const handleNavigate = useCallback(
    (path: string) => {
      void loadDetail(path)
    },
    [loadDetail],
  )

  // Open note from graph: switch to browser tab then load the note
  const handleOpenNoteFromGraph = useCallback(
    (path: string) => {
      setTab('browser')
      void loadDetail(path)
    },
    [loadDetail],
  )

  const handleSync = useCallback(async () => {
    setSyncing(true)
    try {
      const result = await syncVault()
      const { import: imp, export: exp } = result
      const msg = `取り込み ${imp.imported} 件 / 競合 ${imp.conflicts} 件 / 書き出し ${exp.written} 件`
      if (imp.conflicts + imp.rejected > 0) {
        toast.warning(`${msg}（.conflict.md を確認してください）`)
      } else {
        toast.success(msg)
      }
      // Re-fetch notes list and open note (if any)
      await loadNotes(true)
      if (selectedPath) {
        await loadDetail(selectedPath)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '同期に失敗しました。')
    } finally {
      setSyncing(false)
    }
  }, [loadNotes, loadDetail, selectedPath])

  const isEmpty = !loading && !error && (!vaultExists || notes.length === 0)

  const PAGE_TABS = [
    { value: 'browser' as PageTab, label: 'ブラウザ' },
    { value: 'graph' as PageTab, label: 'グラフ' },
  ]

  return (
    <>
      <PageHeader
        title={
          <div className="flex items-center gap-2">
            <BookMarked size={18} />
            ナレッジ（Vault）
          </div>
        }
        subtitle="Obsidian 互換のナレッジ Vault を閲覧・編集できます。インサイト・プレイブック・アウトカムなどのノートを一覧表示します。"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void handleSync()}
              disabled={syncing || loading}
              aria-label="同期"
            >
              {syncing ? '同期中…' : '同期'}
            </button>
            <RefreshButton onClick={() => void loadNotes(true)} busy={refreshing || loading} />
          </div>
        }
      />

      <div className="page-content flex flex-col gap-4">
        {/* Updated Phase 2 notice */}
        <div
          className="flex items-start gap-2 rounded border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-300"
          role="note"
          aria-label="編集と同期について"
        >
          <Info size={15} className="shrink-0 mt-0.5" />
          <span>
            <strong>vault-canonical ノート</strong>（canonical: vault）はアプリ内で直接編集できます。
            Obsidian 側の編集は「同期」ボタンで取り込めます。
            JSON ミラーノート（確定収益・アウトカムなど）は読み取り専用のままです。
          </span>
        </div>

        {/* Top-level tabs: ブラウザ / グラフ */}
        <Tabs tabs={PAGE_TABS} value={tab} onChange={setTab} ariaLabel="Vault ビュー切り替え" />

        {tab === 'browser' ? (
          <AsyncBoundary
            loading={loading}
            error={!loading ? error : null}
            onRetry={() => void loadNotes()}
            loadingText="Vault を読み込み中…"
            errorTitle="Vault の読み込みに失敗しました"
            isEmpty={isEmpty}
            emptyIcon={BookMarked}
            emptyTitle="まだ Vault がありません"
            emptyHint={
              <span>
                ターミナルで{' '}
                <code className="mono text-xs bg-white/10 px-1 py-0.5 rounded">
                  pantheon vault export
                </code>{' '}
                を実行すると生成されます。
                {vaultDir ? (
                  <span className="block text-xs text-muted mt-1">
                    Vault ディレクトリ: <span className="mono">{vaultDir}</span>
                  </span>
                ) : null}
              </span>
            }
          >
            {/* Master / detail layout */}
            <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4 items-start">
              {/* Left: note list */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title text-sm">ノート一覧</div>
                  <span className="badge badge-neutral text-xs">{notes.length} 件</span>
                </div>
                <div className="card-body">
                  <NoteList
                    notes={notes}
                    selected={selectedPath}
                    onSelect={(path) => void loadDetail(path)}
                  />
                </div>
              </div>

              {/* Right: detail */}
              <div className="card">
                <div className="card-body">
                  <AsyncBoundary
                    loading={detailLoading}
                    error={detailError}
                    onRetry={selectedPath ? () => void loadDetail(selectedPath) : undefined}
                    loadingText="ノートを読み込み中…"
                    errorTitle="ノートの読み込みに失敗しました"
                  >
                    {detail ? (
                      <NoteDetail
                        detail={detail}
                        onNavigate={handleNavigate}
                        onReload={(path) => void loadDetail(path)}
                      />
                    ) : (
                      <div className="empty-state">
                        <BookMarked className="empty-state-icon" size={28} />
                        <h3>ノートを選択してください</h3>
                        <p>左のリストからノートを選ぶと内容が表示されます。</p>
                      </div>
                    )}
                  </AsyncBoundary>
                </div>
              </div>
            </div>
          </AsyncBoundary>
        ) : null}

        {tab === 'graph' ? (
          <GraphTab onOpenNote={handleOpenNoteFromGraph} />
        ) : null}
      </div>
    </>
  )
}
