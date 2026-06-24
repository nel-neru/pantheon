import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertTriangle, BookMarked, ExternalLink, Info } from 'lucide-react'

import { api } from '@/lib/api'
import type { VaultNoteDetail, VaultNotesResponse, VaultNoteSummary, VaultWikiLink } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { PageHeader } from '@/components/PageHeader'
import { RefreshButton } from '@/components/RefreshButton'
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
}: {
  detail: VaultNoteDetail
  onNavigate: (path: string) => void
}) {
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
      {/* Title + badges */}
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold leading-tight">{detail.title}</h1>
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

      {/* Markdown body */}
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

// ─── Main Page ────────────────────────────────────────────────────────────────

export function KnowledgePage() {
  const [notes, setNotes] = useState<VaultNoteSummary[]>([])
  const [vaultDir, setVaultDir] = useState<string>('')
  const [vaultExists, setVaultExists] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

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

  const isEmpty = !loading && !error && (!vaultExists || notes.length === 0)

  return (
    <>
      <PageHeader
        title={
          <div className="flex items-center gap-2">
            <BookMarked size={18} />
            ナレッジ（Vault）
          </div>
        }
        subtitle="Obsidian 互換のナレッジ Vault を閲覧できます。インサイト・プレイブック・アウトカムなどのノートを一覧表示します。"
        actions={
          <RefreshButton onClick={() => void loadNotes(true)} busy={refreshing || loading} />
        }
      />

      <div className="page-content flex flex-col gap-4">
        {/* Phase 1 read-only notice */}
        <div
          className="flex items-start gap-2 rounded border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-300"
          role="note"
          aria-label="Phase 1 読み取り専用"
        >
          <Info size={15} className="shrink-0 mt-0.5" />
          <span>
            <strong>Phase 1 は読み取り専用</strong> —
            編集は Obsidian アプリで行ってください。双方向の書き戻し（編集の反映）は Phase 2 で対応予定です。
          </span>
        </div>

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
                    <NoteDetail detail={detail} onNavigate={handleNavigate} />
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
      </div>
    </>
  )
}
