import * as Dialog from '@radix-ui/react-dialog'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import {
  Bot,
  ChevronRight,
  ClipboardCopy,
  FileText,
  FolderOpen,
  Lock,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PageHeader } from '@/components/PageHeader'
import { ScoreBar } from '@/components/ScoreBar'
import { formatDateTime } from '@/lib/utils'
import { priorityBadge, priorityLabel, statusBadge, statusLabel } from '@/lib/labels'

type Organization = {
  id: string
  name: string
  purpose: string
  health_score: number
  autonomy_score: number
  total_agents: number
  pending_proposals: number
  target_repo_path: string
  management_mode?: string
  workspace_path?: string | null
  data_location?: string | null
  initial_kpis?: string[]
  status: string
  last_active: string | null
  is_system?: boolean
  icon_data?: string
}

type TreeAgent = {
  id: string
  name: string
  skills: string[]
  performance_score: number
  current_task?: string | null
}

type TreeTeam = {
  id: string
  name: string
  division_type: string
  mission?: string
  depends_on?: string | null
  agents: TreeAgent[]
}

type TreeDivision = {
  id: string
  name: string
  type: string
  mission?: string
  teams: TreeTeam[]
}

type OrgDetail = Organization & {
  agents: { id: string; name: string; capability_id: string; skills: string[] }[]
  divisions: TreeDivision[]
}

type Proposal = {
  id: string
  title: string
  description: string
  priority: string
  status: string
  file_path: string
}

type OrgForm = { name: string; purpose: string; target_repo_path: string }
type EditForm = { purpose: string; target_repo_path: string }

const initialForm: OrgForm = { name: '', purpose: '', target_repo_path: '' }

/**
 * OrgIcon — アイコン更新時のみ version を bump する（Date.now() 常時キャッシュ破棄を廃止）。
 * iconData が変わったときに setVersion(Date.now()) することで 1 回だけ再取得させる。
 */
function OrgIcon({
  orgName,
  iconData,
  size = 32,
  iconVersion,
}: {
  orgName: string
  iconData?: string
  size?: number
  iconVersion: number
}) {
  const [errored, setErrored] = useState(false)

  useEffect(() => {
    setErrored(false)
  }, [orgName, iconData])

  const src = iconData?.startsWith('data:')
    ? iconData
    : `/api/organizations/${encodeURIComponent(orgName)}/icon?v=${iconVersion}`

  if (errored) {
    return (
      <div
        className="org-icon org-icon-fallback"
        aria-label={`${orgName} icon fallback`}
      >
        {orgName.slice(0, 2).toUpperCase()}
      </div>
    )
  }

  return (
    <img
      className="org-icon"
      src={src}
      alt={orgName}
      width={size}
      height={size}
      onError={() => setErrored(true)}
    />
  )
}

/** Radix Dialog ベースの汎用モーダル（Esc・フォーカストラップ・aria-modal 標準装備） */
function OrgModal({
  open,
  title,
  description,
  children,
  onClose,
}: {
  open: boolean
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-modal="true">
          <Dialog.Title className="dialog-title">{title}</Dialog.Title>
          {description ? (
            <Dialog.Description className="dialog-desc">{description}</Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function OrganizationTree({ divisions }: { divisions: TreeDivision[] }) {
  if (divisions.length === 0) {
    return <div className="text-muted text-sm">Division / Team / Agent の階層データはまだありません。</div>
  }

  return (
    <div className="flex flex-col gap-3">
      {divisions.map((division) => (
        <details key={division.id} open className="card org-tree-card">
          <summary className="flex items-center justify-between gap-3 cursor-pointer px-4 py-3">
            <div>
              <div className="font-semibold">{division.name}</div>
              <div className="text-xs text-muted">{division.type}</div>
            </div>
            <span className="badge badge-neutral text-xs">{division.teams.length} teams</span>
          </summary>
          <div className="px-4 pb-4 flex flex-col gap-3">
            {division.teams.map((team) => (
              <details key={team.id} open className="ml-3">
                <summary className="flex items-center justify-between gap-3 cursor-pointer py-2">
                  <div>
                    <div className="font-medium">{team.name}</div>
                    <div className="text-xs text-muted">{team.mission ?? 'ミッション未設定'}</div>
                  </div>
                  <span className="badge badge-blue text-xs">{team.agents.length} agents</span>
                </summary>
                <div className="flex flex-col gap-2 pt-2 ml-3">
                  {team.agents.map((agent) => (
                    <div key={agent.id} className="org-tree-agent-row">
                      <div>
                        <div className="flex items-center gap-2">
                          <Bot size={12} />
                          <span className="font-medium">{agent.name}</span>
                        </div>
                        <div className="text-xs text-muted mt-1">{agent.skills.join(' / ') || 'skill 未設定'}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </details>
      ))}
    </div>
  )
}

/**
 * 依存マップ — depends_on がある Team のみ列挙する（擬似フロー図廃止）。
 * 実際の depends_on がないチームは「依存関係なし」を示す。
 */
function DependencyList({ divisions }: { divisions: TreeDivision[] }) {
  const deps = divisions.flatMap((div) =>
    div.teams
      .filter((t) => t.depends_on)
      .map((t) => ({ teamName: t.name, dependsOn: t.depends_on as string, divisionName: div.name }))
  )

  if (deps.length === 0) {
    return <div className="text-muted text-sm">定義された依存関係はありません。</div>
  }

  return (
    <ul className="flex flex-col gap-2 text-sm">
      {deps.map((d) => (
        <li key={`${d.divisionName}-${d.teamName}`} className="flex items-center gap-2">
          <span className="badge badge-neutral">{d.divisionName}</span>
          <span className="font-medium">{d.teamName}</span>
          <span className="text-muted">→ 依存:</span>
          <span className="badge badge-blue">{d.dependsOn}</span>
        </li>
      ))}
    </ul>
  )
}

function DetailPanel({
  org,
  onClose,
  onEdit,
  onDelete,
  onMigrate,
  migrating,
  fileInputRef,
  onIconUpload,
  onResetIcon,
  iconBusy,
  iconVersion,
}: {
  org: OrgDetail
  onClose: () => void
  onEdit: () => void
  onDelete: () => void
  onMigrate: (orgName: string) => Promise<void>
  migrating: boolean
  fileInputRef: RefObject<HTMLInputElement | null>
  onIconUpload: (e: ChangeEvent<HTMLInputElement>, orgName: string) => Promise<void>
  onResetIcon: (orgName: string) => Promise<void>
  iconBusy: boolean
  iconVersion: number
}) {
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [loadingProposals, setLoadingProposals] = useState(true)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [confirmMigrate, setConfirmMigrate] = useState(false)
  const [confirmResetIcon, setConfirmResetIcon] = useState(false)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    setLoadingProposals(true)
    setProposalError(null)
    api<Proposal[]>('GET', `/api/organizations/${encodeURIComponent(org.name)}/proposals`)
      .then(setProposals)
      .catch((err: unknown) => {
        setProposalError(err instanceof Error ? err.message : '提案の読み込みに失敗しました。')
        setProposals([])
      })
      .finally(() => setLoadingProposals(false))
  }, [org.name])

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path)
      toast.success('パスをコピーしました。')
    } catch {
      toast.error('クリップボードへのコピーに失敗しました。')
    }
  }

  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="detail-panel-overlay" onClick={onClose} />
        <Dialog.Content
          className="detail-panel"
          aria-modal="true"
          onOpenAutoFocus={(e) => {
            e.preventDefault()
            closeRef.current?.focus()
          }}
        >
          <Dialog.Title className="sr-only">{org.name} 詳細</Dialog.Title>
          <Dialog.Description className="sr-only">{org.purpose}</Dialog.Description>

          {/* Header */}
          <div className="detail-panel-header">
            <div className="detail-panel-title-row">
              <div className="detail-panel-title">{org.name}</div>
              <div className="detail-panel-actions">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-icon"
                  onClick={onEdit}
                  aria-label="編集"
                >
                  <Pencil size={13} />
                </button>
                {org.is_system ? (
                  <span className="badge badge-neutral flex items-center gap-1">
                    <Lock size={11} />
                    システム
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-icon"
                    onClick={onDelete}
                    aria-label="削除"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
                <button
                  ref={closeRef}
                  type="button"
                  className="btn btn-ghost btn-sm btn-icon"
                  onClick={onClose}
                  aria-label="閉じる"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="detail-panel-subtitle">{org.purpose}</div>
          </div>

          {/* Body */}
          <div className="detail-panel-body">
            {/* Icon section */}
            <section className="detail-section">
              <div className="detail-section-label">アイコン</div>
              <div className="detail-org-icon-row">
                <OrgIcon orgName={org.name} iconData={org.icon_data} size={48} iconVersion={iconVersion} />
                <div className="detail-org-icon-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={iconBusy}
                  >
                    アイコン変更
                  </button>
                  {org.icon_data ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setConfirmResetIcon(true)}
                      disabled={iconBusy}
                    >
                      リセット
                    </button>
                  ) : null}
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                className="hidden"
                onChange={(e) => void onIconUpload(e, org.name)}
              />
            </section>

            {/* Metrics row */}
            <div className="detail-metrics">
              <div className="detail-metric">
                <div className="metric-label">健康スコア</div>
                <ScoreBar score={org.health_score} label="健康スコア" />
              </div>
              <div className="detail-metric">
                <div className="metric-label">自律スコア</div>
                <ScoreBar score={org.autonomy_score} label="自律スコア" />
              </div>
              <div className="detail-metric">
                <div className="metric-label">エージェント数</div>
                <div className="detail-metric-val">{org.total_agents}</div>
              </div>
              <div className="detail-metric">
                <div className="metric-label">未対応提案</div>
                <div className={org.pending_proposals > 0 ? 'detail-metric-val text-yellow' : 'detail-metric-val'}>
                  {org.pending_proposals > 0 ? (
                    <Link
                      to={`/improvements?org=${encodeURIComponent(org.name)}`}
                      className="underline"
                    >
                      {org.pending_proposals}
                    </Link>
                  ) : (
                    '0'
                  )}
                </div>
              </div>
            </div>

            {/* Info */}
            <section className="detail-section">
              <div className="detail-section-label">基本情報</div>
              <div className="detail-kv">
                <div className="detail-kv-row">
                  <FolderOpen size={13} />
                  <span className="detail-kv-key">ワークスペース</span>
                  {org.target_repo_path ? (
                    <span className="detail-kv-val mono truncate" title={org.target_repo_path}>
                      {org.target_repo_path}
                    </span>
                  ) : (
                    <span className="badge badge-yellow">未設定（repo を割り当ててください）</span>
                  )}
                  {org.target_repo_path ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon btn-sm"
                      onClick={() => void copyPath(org.target_repo_path)}
                      aria-label="パスをコピー"
                      title="コピー"
                    >
                      <ClipboardCopy size={12} />
                    </button>
                  ) : null}
                </div>
                <div className="detail-kv-row">
                  <span className="detail-kv-key ml-4">管理モード</span>
                  {org.management_mode === 'workspace' ? (
                    <span className="badge badge-blue">workspace（git 不要）</span>
                  ) : (
                    <>
                      <span className="badge badge-neutral">repo（git 管理）</span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm ml-4"
                        disabled={migrating}
                        onClick={() => setConfirmMigrate(true)}
                      >
                        {migrating ? '移行中…' : 'workspace へ移行'}
                      </button>
                    </>
                  )}
                </div>
                <div className="detail-kv-row">
                  <span className="detail-kv-key ml-4">ステータス</span>
                  <span className={`badge ${statusBadge(org.status)}`}>
                    {statusLabel(org.status)}
                  </span>
                </div>
                <div className="detail-kv-row">
                  <span className="detail-kv-key ml-4">最終活動</span>
                  <span className="detail-kv-val">{formatDateTime(org.last_active)}</span>
                </div>
              </div>
            </section>

            {org.initial_kpis && org.initial_kpis.length > 0 ? (
              <section className="detail-section">
                <div className="detail-section-label">初期KPI</div>
                <div className="flex flex-wrap gap-2">
                  {org.initial_kpis.map((kpi) => (
                    <span key={kpi} className="badge badge-blue">{kpi}</span>
                  ))}
                </div>
              </section>
            ) : null}

            {/* Agents */}
            {org.agents.length > 0 && (
              <section className="detail-section">
                <div className="detail-section-label">
                  <Bot size={12} />
                  エージェント
                </div>
                <div className="detail-agents-list">
                  {org.agents.map((a) => (
                    <div key={a.id} className="detail-agent-row">
                      <div className="detail-agent-name">{a.name}</div>
                      <div className="mono text-muted text-xs">{a.capability_id}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Dependency map — simplified to actual depends_on only */}
            <section className="detail-section">
              <div className="detail-section-label">依存関係</div>
              <DependencyList divisions={org.divisions ?? []} />
            </section>

            {/* Org tree */}
            <section className="detail-section">
              <div className="detail-section-label">組織ツリー</div>
              <OrganizationTree divisions={org.divisions ?? []} />
            </section>

            {/* Proposals */}
            <section className="detail-section">
              <div className="detail-section-label">
                <FileText size={12} />
                未対応の改善提案
              </div>
              {loadingProposals ? (
                <div className="text-muted text-sm">読み込み中…</div>
              ) : proposalError ? (
                <div className="text-sm text-red">{proposalError}</div>
              ) : proposals.length === 0 ? (
                <div className="text-muted text-sm">
                  未対応の提案はありません。
                  <Link
                    to={`/improvements?org=${encodeURIComponent(org.name)}`}
                    className="ml-2 underline text-muted text-sm"
                  >
                    提案を分析する →
                  </Link>
                </div>
              ) : (
                <div className="detail-proposals-list">
                  {proposals.map((p) => (
                    <div key={p.id} className="detail-proposal-row">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`badge ${priorityBadge(p.priority)}`}>
                          {priorityLabel(p.priority)}
                        </span>
                        <span className="detail-proposal-title">{p.title}</span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {p.file_path ? (
                          <span className="mono text-muted detail-proposal-file">{p.file_path}</span>
                        ) : null}
                        <Link
                          to={`/improvements?org=${encodeURIComponent(org.name)}&proposal=${encodeURIComponent(p.id)}`}
                          className="btn btn-ghost btn-sm"
                        >
                          承認インボックスで開く →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </Dialog.Content>
      </Dialog.Portal>

      {/* Migrate to workspace confirm */}
      <ConfirmDialog
        open={confirmMigrate}
        onOpenChange={setConfirmMigrate}
        title="workspace へ移行"
        description={
          <>
            <strong>{org.name}</strong> を workspace モードへ移行します。
            <br />
            この操作により git 管理が不要になりますが、<strong>元に戻すことはできません</strong>。
            移行前に未コミットの変更がないことを確認してください。
          </>
        }
        confirmLabel="移行する"
        destructive
        onConfirm={() => onMigrate(org.name)}
      />

      {/* Reset icon confirm */}
      <ConfirmDialog
        open={confirmResetIcon}
        onOpenChange={setConfirmResetIcon}
        title="アイコンをリセット"
        description="設定済みのアイコンを削除します。この操作は元に戻せません。"
        confirmLabel="リセット"
        destructive
        onConfirm={() => onResetIcon(org.name)}
      />
    </Dialog.Root>
  )
}

function getDetailLoadErrorMessage(error: unknown, orgName: string) {
  if (error instanceof Error) {
    if (error.message.includes('見つかりません') || error.message.includes('404')) {
      return `組織「${orgName}」は見つかりません。一覧を更新して再度お試しください。`
    }
    if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
      return '組織詳細の取得中にネットワークエラーが発生しました。接続を確認して再試行してください。'
    }
    return `組織の詳細を読み込めませんでした: ${error.message}`
  }
  return '組織の詳細を読み込めませんでした。'
}

export function OrgsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState<OrgForm>(initialForm)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState<Organization | null>(null)
  const [detail, setDetail] = useState<OrgDetail | null>(null)
  const [editing, setEditing] = useState<Organization | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ purpose: '', target_repo_path: '' })
  const [updatingIcon, setUpdatingIcon] = useState(false)
  const [migrating, setMigrating] = useState(false)
  // iconVersion is bumped only on successful icon update/reset (not on every render)
  const [iconVersion, setIconVersion] = useState(1)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const loadOrganizations = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const data = await api<Organization[]>('GET', '/api/organizations')
      setOrganizations(data)
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '組織の読み込みに失敗しました。'
      setLoadError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (orgName: string) => {
    try {
      const data = await api<OrgDetail>('GET', `/api/organizations/${encodeURIComponent(orgName)}`)
      setDetail(data)
    } catch (error) {
      setDetail(null)
      toast.error(getDetailLoadErrorMessage(error, orgName))
    }
  }, [])

  const refreshOrganizations = useCallback(async (orgName?: string) => {
    await loadOrganizations(true)
    if (orgName) {
      await loadDetail(orgName)
    }
  }, [loadDetail, loadOrganizations])

  useEffect(() => {
    void loadOrganizations()
  }, [loadOrganizations])

  const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (event) => resolve((event.target?.result as string) ?? '')
    reader.onerror = () => reject(new Error('アイコンファイルの読み込みに失敗しました。'))
    reader.readAsDataURL(file)
  })

  const handleIconUpload = async (e: ChangeEvent<HTMLInputElement>, orgName: string) => {
    const input = e.target
    const file = input.files?.[0]
    if (!file) return

    setUpdatingIcon(true)
    try {
      const iconData = await readFileAsDataUrl(file)
      await api('PUT', `/api/organizations/${encodeURIComponent(orgName)}/icon`, { icon_data: iconData })
      setIconVersion((v) => v + 1)
      toast.success('アイコンを更新しました。')
      await refreshOrganizations(orgName)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'アイコンの更新に失敗しました。')
    } finally {
      input.value = ''
      setUpdatingIcon(false)
    }
  }

  const resetIcon = async (orgName: string) => {
    setUpdatingIcon(true)
    try {
      await api('DELETE', `/api/organizations/${encodeURIComponent(orgName)}/icon`)
      setIconVersion((v) => v + 1)
      toast.success('アイコンをリセットしました。')
      await refreshOrganizations(orgName)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'アイコンのリセットに失敗しました。')
      throw error
    } finally {
      setUpdatingIcon(false)
    }
  }

  const handleSelectDetail = (org: Organization) => {
    void loadDetail(org.name)
  }

  const migrateToWorkspace = async (orgName: string) => {
    setMigrating(true)
    try {
      const res = await api<{ already_workspace: boolean }>(
        'POST',
        `/api/organizations/${encodeURIComponent(orgName)}/migrate-to-workspace`
      )
      toast.success(
        res.already_workspace
          ? `${orgName} は既に workspace モードです。`
          : `${orgName} を workspace モードへ移行しました（git 管理が不要になります）。`
      )
      await refreshOrganizations(orgName)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'workspace への移行に失敗しました。')
      throw error
    } finally {
      setMigrating(false)
    }
  }

  const confirmDelete = (org: Organization) => {
    if (org.is_system) return
    setDeleting(org)
    setDetail(null)
  }

  const closeCreate = () => {
    if (!submitting) {
      setShowCreate(false)
      setCreateForm(initialForm)
    }
  }

  const handleCreate = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!createForm.target_repo_path.trim()) {
      toast.error('対象ワークスペース（repo）は必須です。')
      return
    }
    setSubmitting(true)
    try {
      await api('POST', '/api/organizations', createForm)
      toast.success('組織を作成しました。')
      setCreateForm(initialForm)
      setShowCreate(false)
      await loadOrganizations()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '組織の作成に失敗しました。')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleting) return
    await api('DELETE', `/api/organizations/${encodeURIComponent(deleting.name)}`)
    toast.success('組織を削除しました。')
    setDeleting(null)
    setDetail(null)
    await loadOrganizations()
  }

  const openEdit = (org: Organization) => {
    setEditing(org)
    setEditForm({ purpose: org.purpose, target_repo_path: org.target_repo_path })
    setDetail(null)
  }

  const handleEdit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!editing) return
    setSubmitting(true)
    try {
      await api('PUT', `/api/organizations/${encodeURIComponent(editing.name)}`, editForm)
      toast.success('組織を更新しました。')
      setEditing(null)
      await loadOrganizations()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '組織の更新に失敗しました。')
    } finally {
      setSubmitting(false)
    }
  }

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText('pantheon org scan')
      toast.success('コマンドをコピーしました。')
    } catch {
      toast.error('クリップボードへのコピーに失敗しました。')
    }
  }

  return (
    <>
      <PageHeader
        title="組織"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            新規組織
          </button>
        }
      />

      <div className="page-content flex flex-col gap-4">
        <AsyncBoundary
          loading={loading}
          error={loadError}
          onRetry={() => void loadOrganizations()}
          loadingText="組織を読み込み中…"
          errorTitle="組織の読み込みに失敗しました"
        >
          {organizations.length === 0 ? (
            <div className="welcome-card">
              <div className="welcome-card-body">
                <div className="welcome-header">
                  <div className="welcome-icon">
                    <Sparkles size={22} />
                  </div>
                  <h2 className="welcome-title">Pantheon へようこそ</h2>
                  <p className="welcome-desc">
                    AI 組織を作成して、コードの自律的な分析・改善を始めましょう。
                    担当する git リポジトリ（ワークスペース）を指定して組織を作成してください。
                  </p>
                </div>
                <div className="welcome-actions flex items-center gap-2">
                  <Link to="/onboarding" className="btn btn-primary">
                    <Sparkles size={14} />
                    副業ポートフォリオを自動構築
                  </Link>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowCreate(true)}
                  >
                    <Plus size={14} />
                    組織を作成
                  </button>
                </div>
                <p className="welcome-note">
                  既存のリポジトリは{' '}
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void copyCommand()}
                    title="クリックでコピー"
                  >
                    <ClipboardCopy size={12} />
                    <code>pantheon org scan</code>
                  </button>
                  {' '}で一括登録できます（クリックでコマンドをコピー）。
                </p>
              </div>
            </div>
          ) : null}
          {organizations.length > 0 ? <div className="org-list">
            {organizations.map((org) => (
              <div key={org.name} className="org-list-item">
                <OrgIcon orgName={org.name} iconData={org.icon_data} iconVersion={iconVersion} />

                <div className="org-list-main">
                  <div className="org-list-name">{org.name}</div>
                  {org.purpose ? <div className="org-list-purpose">{org.purpose}</div> : null}
                </div>

                <div className="org-list-scores">
                  <div className="flex flex-col gap-1">
                    <div className="score-bar-label text-xs text-muted">健康</div>
                    <ScoreBar
                      score={org.health_score}
                      label="健康スコア"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <div className="score-bar-label text-xs text-muted">自律</div>
                    <ScoreBar
                      score={org.autonomy_score}
                      label="自律スコア"
                    />
                  </div>
                </div>

                <div className="org-list-meta">
                  <span className={`badge text-xs ${statusBadge(org.status)}`}>
                    {statusLabel(org.status)}
                  </span>
                  <span className="text-xs text-muted">{org.total_agents} エージェント</span>
                  {org.pending_proposals > 0 ? (
                    <button
                      type="button"
                      className="badge badge-yellow text-xs cursor-pointer"
                      onClick={() => handleSelectDetail(org)}
                      aria-label={`${org.pending_proposals} 件の未対応提案を開く`}
                      title="未対応提案を表示"
                    >
                      {org.pending_proposals} 提案
                    </button>
                  ) : null}
                  {org.last_active ? (
                    <span className="text-xs text-muted">{formatDateTime(org.last_active)}</span>
                  ) : null}
                </div>

                <div className="org-list-actions">
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => openEdit(org)}
                    aria-label={`${org.name} を編集`}
                    title="編集"
                  >
                    <Pencil size={14} />
                  </button>
                  {org.is_system ? (
                    <span className="flex items-center gap-1 text-muted">
                      <Lock size={13} aria-hidden="true" />
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon btn-sm text-red"
                      onClick={() => confirmDelete(org)}
                      aria-label={`${org.name} を削除`}
                      title="削除"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon btn-sm"
                    onClick={() => handleSelectDetail(org)}
                    aria-label={`${org.name} の詳細を開く`}
                    title="詳細を開く"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div> : null}
        </AsyncBoundary>
      </div>

      {/* Detail side panel (Radix Dialog) */}
      {detail ? (
        <DetailPanel
          org={detail}
          onClose={() => setDetail(null)}
          onEdit={() => openEdit(detail)}
          onDelete={() => confirmDelete(detail)}
          onMigrate={migrateToWorkspace}
          migrating={migrating}
          fileInputRef={fileInputRef}
          onIconUpload={handleIconUpload}
          onResetIcon={resetIcon}
          iconBusy={updatingIcon}
          iconVersion={iconVersion}
        />
      ) : null}

      {/* Create modal (Radix Dialog) */}
      <OrgModal
        open={showCreate}
        title="新規組織"
        description="1 組織 = 1 ワークスペース（git リポジトリ）。担当 repo は必須です。"
        onClose={closeCreate}
      >
        <form onSubmit={handleCreate} className="flex flex-col gap-4">
          <div className="input-group">
            <label className="input-label" htmlFor="org-name">名前</label>
            <input
              id="org-name"
              className="input"
              value={createForm.name}
              onChange={(e) => setCreateForm((c) => ({ ...c, name: e.target.value }))}
              placeholder="acme-platform"
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="org-purpose">目的</label>
            <textarea
              id="org-purpose"
              className="textarea"
              value={createForm.purpose}
              onChange={(e) => setCreateForm((c) => ({ ...c, purpose: e.target.value }))}
              placeholder="組織のミッションとコードベースの焦点を記述してください"
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="org-repo-path">
              対象ワークスペース（git リポジトリ）の絶対パス
            </label>
            <input
              id="org-repo-path"
              className="input"
              value={createForm.target_repo_path}
              onChange={(e) => setCreateForm((c) => ({ ...c, target_repo_path: e.target.value }))}
              placeholder="C:\\Users\\name\\projects\\repo"
              required
            />
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={closeCreate}
              disabled={submitting}
            >
              キャンセル
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <Plus size={14} />
              {submitting ? '作成中' : '作成'}
            </button>
          </div>
        </form>
      </OrgModal>

      {/* Edit modal (Radix Dialog) */}
      <OrgModal
        open={Boolean(editing)}
        title="組織を編集"
        description={`${editing?.name ?? ''} の情報を変更します。`}
        onClose={() => {
          if (!submitting) setEditing(null)
        }}
      >
        <form onSubmit={handleEdit} className="flex flex-col gap-4">
          <div className="input-group">
            <label className="input-label" htmlFor="edit-purpose">目的</label>
            <textarea
              id="edit-purpose"
              className="textarea"
              value={editForm.purpose}
              onChange={(e) => setEditForm((c) => ({ ...c, purpose: e.target.value }))}
              required
            />
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor="edit-repo-path">対象リポジトリパス</label>
            <input
              id="edit-repo-path"
              className="input"
              value={editForm.target_repo_path}
              onChange={(e) => setEditForm((c) => ({ ...c, target_repo_path: e.target.value }))}
              placeholder="C:\\Users\\name\\projects\\repo"
            />
            <p className="text-xs text-muted mt-1">
              パスを変更すると組織に紐づくワークスペースが切り替わります。必要に応じて確認してください。
            </p>
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => { if (!submitting) setEditing(null) }}
              disabled={submitting}
            >
              キャンセル
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <Pencil size={14} />
              {submitting ? '更新中' : '保存'}
            </button>
          </div>
        </form>
      </OrgModal>

      {/* Delete confirm (ConfirmDialog with confirmWord) */}
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => { if (!next) setDeleting(null) }}
        title="組織を削除"
        description={
          <>
            組織「<strong>{deleting?.name}</strong>」を削除しますか？この操作は取り消せません。
          </>
        }
        confirmLabel="削除する"
        destructive
        confirmWord={deleting?.name}
        confirmWordLabel={
          <>
            確認のため、組織名 <code>{deleting?.name}</code> を入力してください
          </>
        }
        onConfirm={handleDelete}
      />
    </>
  )
}
