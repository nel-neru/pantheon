import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import {
  Bot,
  ChevronRight,
  FileText,
  FolderOpen,
  Lock,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { formatDate, healthClass } from '@/lib/utils'

type Organization = {
  id: string
  name: string
  purpose: string
  health_score: number
  autonomy_score: number
  total_agents: number
  pending_proposals: number
  target_repo_path: string
  status: string
  last_active: string | null
  is_system?: boolean
  icon_data?: string
}

type OrgDetail = Organization & {
  agents: { id: string; name: string; capability_id: string; skills: string[] }[]
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

function ScoreTooltip({
  label,
  score,
  description,
}: {
  label: string
  score: number
  description: string
}) {
  const normalizedScore = Math.max(0, Math.min(100, Math.round(score)))
  const colorClass = normalizedScore >= 70 ? 'score-high' : normalizedScore >= 40 ? 'score-mid' : 'score-low'

  return (
    <div className="score-wrapper">
      <div className="score-bar-container tooltip-trigger" aria-label={`${label}スコア ${normalizedScore}`} tabIndex={0}>
        <div className="score-bar-label">{label}</div>
        <div className="score-bar-track" aria-hidden="true">
          <div className={`score-bar-fill ${colorClass}`} style={{ width: `${normalizedScore}%` }} />
        </div>
        <div className="score-bar-value">{normalizedScore}</div>
        <div className="tooltip-content" role="tooltip">{description}</div>
      </div>
    </div>
  )
}

function OrgIcon({
  orgName,
  iconData,
  size = 32,
}: {
  orgName: string
  iconData?: string
  size?: number
}) {
  const [errored, setErrored] = useState(false)
  const [version, setVersion] = useState(() => Date.now())

  useEffect(() => {
    setErrored(false)
    setVersion(Date.now())
  }, [orgName, iconData])

  const src = iconData?.startsWith('data:')
    ? iconData
    : `/api/organizations/${encodeURIComponent(orgName)}/icon?v=${version}`

  if (errored) {
    return (
      <div
        className="org-icon org-icon-fallback"
        aria-label={`${orgName} icon fallback`}
        style={{ width: size, height: size }}
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

function Modal({
  open,
  title,
  description,
  children,
  onClose,
}: {
  open: boolean
  title: string
  description: string
  children: ReactNode
  onClose: () => void
}) {
  if (!open) return null
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-title">{title}</div>
        <div className="dialog-desc">{description}</div>
        {children}
      </div>
    </div>
  )
}

function DetailPanel({
  org,
  onClose,
  onEdit,
  onDelete,
  fileInputRef,
  onIconUpload,
  onResetIcon,
  iconBusy,
}: {
  org: OrgDetail
  onClose: () => void
  onEdit: () => void
  onDelete: () => void
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onIconUpload: (e: React.ChangeEvent<HTMLInputElement>, orgName: string) => Promise<void>
  onResetIcon: (orgName: string) => Promise<void>
  iconBusy: boolean
}) {
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [loadingProposals, setLoadingProposals] = useState(true)

  useEffect(() => {
    setLoadingProposals(true)
    api<Proposal[]>('GET', `/api/organizations/${encodeURIComponent(org.name)}/proposals`)
      .then(setProposals)
      .catch(() => setProposals([]))
      .finally(() => setLoadingProposals(false))
  }, [org.name])

  return (
    <div className="detail-panel-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
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
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-icon"
                  disabled
                  title="システム組織は削除できません"
                  aria-label="システム組織は削除できません"
                  style={{ opacity: 0.3, cursor: 'not-allowed' }}
                >
                  <Lock size={13} />
                </button>
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
          <section className="detail-section">
            <div className="detail-section-label">アイコン</div>
            <div className="detail-org-icon-row">
              <OrgIcon orgName={org.name} iconData={org.icon_data} size={48} />
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
                    onClick={() => void onResetIcon(org.name)}
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
              style={{ display: 'none' }}
              onChange={(e) => void onIconUpload(e, org.name)}
            />
          </section>

          {/* Metrics row */}
          <div className="detail-metrics">
            <div className="detail-metric">
              <div className="metric-label">健康スコア</div>
              <div className={`detail-metric-val ${healthClass(org.health_score)}`}>
                {org.health_score.toFixed(0)}
              </div>
              <div className="health-track mt-1">
                <div
                  className={`health-fill ${healthClass(org.health_score)}`}
                  style={{ width: `${org.health_score}%` }}
                />
              </div>
            </div>
            <div className="detail-metric">
              <div className="metric-label">自律スコア</div>
              <div className="detail-metric-val">{org.autonomy_score.toFixed(0)}</div>
            </div>
            <div className="detail-metric">
              <div className="metric-label">エージェント数</div>
              <div className="detail-metric-val">{org.total_agents}</div>
            </div>
            <div className="detail-metric">
              <div className="metric-label">未対応提案</div>
              <div className="detail-metric-val">{org.pending_proposals}</div>
            </div>
          </div>

          {/* Info */}
          <section className="detail-section">
            <div className="detail-section-label">基本情報</div>
            <div className="detail-kv">
              <div className="detail-kv-row">
                <FolderOpen size={13} />
                <span className="detail-kv-key">リポジトリ</span>
                <span className="detail-kv-val mono">{org.target_repo_path || '未設定'}</span>
              </div>
              <div className="detail-kv-row">
                <span className="detail-kv-key ml-4">ステータス</span>
                <span className="badge badge-neutral">{org.status}</span>
              </div>
              <div className="detail-kv-row">
                <span className="detail-kv-key ml-4">最終活動</span>
                <span className="detail-kv-val">{org.last_active ? formatDate(org.last_active) : '—'}</span>
              </div>
            </div>
          </section>

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
                    <div className="mono text-muted" style={{ fontSize: '11px' }}>{a.capability_id}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Proposals */}
          <section className="detail-section">
            <div className="detail-section-label">
              <FileText size={12} />
              未対応の改善提案
            </div>
            {loadingProposals ? (
              <div className="text-muted text-sm">読み込み中…</div>
            ) : proposals.length === 0 ? (
              <div className="text-muted text-sm">未対応の提案はありません。</div>
            ) : (
              <div className="detail-proposals-list">
                {proposals.map((p) => (
                  <div key={p.id} className="detail-proposal-row">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`badge ${
                          p.priority === 'high'
                            ? 'badge-red'
                            : p.priority === 'medium'
                              ? 'badge-yellow'
                              : 'badge-neutral'
                        }`}
                      >
                        {p.priority}
                      </span>
                      <span className="detail-proposal-title">{p.title}</span>
                    </div>
                    {p.file_path && (
                      <span className="mono text-muted detail-proposal-file">{p.file_path}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

export function OrgsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState<OrgForm>(initialForm)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState<Organization | null>(null)
  const [deleteStep, setDeleteStep] = useState<1 | 2>(1)
  const [deleteConfirmName, setDeleteConfirmName] = useState('')
  const [detail, setDetail] = useState<OrgDetail | null>(null)
  const [editing, setEditing] = useState<Organization | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ purpose: '', target_repo_path: '' })
  const [creatingWelcome, setCreatingWelcome] = useState(false)
  const [updatingIcon, setUpdatingIcon] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const loadOrganizations = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<Organization[]>('GET', '/api/organizations')
      setOrganizations(data)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '組織の読み込みに失敗しました。')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (orgName: string) => {
    try {
      const data = await api<OrgDetail>('GET', `/api/organizations/${encodeURIComponent(orgName)}`)
      setDetail(data)
    } catch {
      toast.error('組織の詳細を読み込めませんでした。')
    }
  }, [])

  const refreshOrganizations = useCallback(async (orgName?: string) => {
    await loadOrganizations()
    if (orgName) {
      await loadDetail(orgName)
    }
  }, [loadDetail, loadOrganizations])

  useEffect(() => {
    void loadOrganizations()
  }, [loadOrganizations])

  const handleCreateWelcome = async () => {
    setCreatingWelcome(true)
    try {
      const res = await api<{ created: string[] }>('POST', '/api/welcome')
      if (res.created.length > 0) {
        toast.success(`サンプル組織「${res.created[0]}」を作成しました。`)
      } else {
        toast.info('サンプル組織はすでに存在します。')
      }
      await loadOrganizations()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'サンプル組織の作成に失敗しました。')
    } finally {
      setCreatingWelcome(false)
    }
  }

  const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (event) => resolve((event.target?.result as string) ?? '')
    reader.onerror = () => reject(new Error('アイコンファイルの読み込みに失敗しました。'))
    reader.readAsDataURL(file)
  })

  const handleIconUpload = async (e: React.ChangeEvent<HTMLInputElement>, orgName: string) => {
    const input = e.target
    const file = input.files?.[0]
    if (!file) return

    setUpdatingIcon(true)
    try {
      const iconData = await readFileAsDataUrl(file)
      await api('PUT', `/api/organizations/${encodeURIComponent(orgName)}/icon`, { icon_data: iconData })
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
      toast.success('アイコンをリセットしました。')
      await refreshOrganizations(orgName)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'アイコンのリセットに失敗しました。')
    } finally {
      setUpdatingIcon(false)
    }
  }

  const handleSelectDetail = (org: Organization) => {
    void loadDetail(org.name)
  }

  const closeDeleteModal = () => {
    setDeleting(null)
    setDeleteStep(1)
    setDeleteConfirmName('')
  }

  const confirmDelete = (org: Organization) => {
    if (org.is_system) return
    setDeleting(org)
    setDeleteStep(1)
    setDeleteConfirmName('')
    setDetail(null)
  }

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
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
    if (!deleting || deleteConfirmName !== deleting.name) return
    setSubmitting(true)
    try {
      await api('DELETE', `/api/organizations/${encodeURIComponent(deleting.name)}`)
      toast.success('組織を削除しました。')
      closeDeleteModal()
      setDetail(null)
      await loadOrganizations()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '組織の削除に失敗しました。')
    } finally {
      setSubmitting(false)
    }
  }

  const openEdit = (org: Organization) => {
    setEditing(org)
    setEditForm({ purpose: org.purpose, target_repo_path: org.target_repo_path })
    setDetail(null)
  }

  const handleEdit = async (e: React.FormEvent<HTMLFormElement>) => {
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

  return (
    <>
      <header className="page-header">
        <div className="page-title">組織</div>
        <div className="page-actions">
          <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            新規組織
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">組織を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && organizations.length === 0 ? (
          <div className="welcome-card">
            <div className="welcome-card-body">
              <div className="welcome-header">
                <div className="welcome-icon">
                  <Sparkles size={22} />
                </div>
                <h2 className="welcome-title">RepoCorp AI へようこそ</h2>
                <p className="welcome-desc">
                  AI 組織を作成して、コードの自律的な分析・改善を始めましょう。
                  まずはサンプル組織を作成して使い方を確認するか、独自の組織を新規作成してください。
                </p>
              </div>
              <div className="welcome-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleCreateWelcome}
                  disabled={creatingWelcome}
                >
                  <Sparkles size={14} />
                  {creatingWelcome ? '作成中…' : 'サンプル組織で始める'}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowCreate(true)}
                >
                  <Plus size={14} />
                  組織を自分で作成
                </button>
              </div>
              <p className="welcome-note">サンプル組織は後からいつでも削除できます。</p>
            </div>
          </div>
        ) : null}

        {organizations.length > 0 ? (
          <div className="org-list">
            {organizations.map((org) => (
              <div
                key={org.name}
                className="org-list-item"
                role="button"
                tabIndex={0}
                aria-label={`${org.name} の詳細を開く`}
                onClick={() => handleSelectDetail(org)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    handleSelectDetail(org)
                  }
                }}
              >
                <OrgIcon orgName={org.name} iconData={org.icon_data} />

                <div className="org-list-main">
                  <div className="org-list-name">{org.name}</div>
                  {org.purpose ? <div className="org-list-purpose">{org.purpose}</div> : null}
                </div>

                <div className="org-list-scores">
                  <ScoreTooltip
                    label="健康"
                    score={org.health_score}
                    description="コードレビュー通過率・改善実行率から算出。100が最高。"
                  />
                  <ScoreTooltip
                    label="自律"
                    score={org.autonomy_score}
                    description="エージェントの自律的な行動・意思決定の頻度から算出。"
                  />
                </div>

                <div className="org-list-meta">
                  <span className="badge badge-neutral text-xs">{org.status}</span>
                  <span className="text-xs text-muted">{org.total_agents} エージェント</span>
                  {org.pending_proposals > 0 ? (
                    <span className="badge badge-yellow text-xs">{org.pending_proposals} 提案</span>
                  ) : null}
                  {org.last_active ? (
                    <span className="text-xs text-muted">{formatDate(org.last_active)}</span>
                  ) : null}
                </div>

                <div className="org-list-actions" onClick={(e) => e.stopPropagation()}>
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
                    <button
                      type="button"
                      className="btn btn-ghost btn-icon btn-sm"
                      disabled
                      aria-label="システム組織は削除できません"
                      title="システム組織は削除できません"
                      style={{ opacity: 0.3, cursor: 'not-allowed' }}
                    >
                      <Lock size={14} />
                    </button>
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
                  <ChevronRight size={14} className="text-muted" aria-hidden="true" />
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Detail side panel */}
      {detail ? (
        <DetailPanel
          org={detail}
          onClose={() => setDetail(null)}
          onEdit={() => openEdit(detail)}
          onDelete={() => confirmDelete(detail)}
          fileInputRef={fileInputRef}
          onIconUpload={handleIconUpload}
          onResetIcon={resetIcon}
          iconBusy={updatingIcon}
        />
      ) : null}

      {/* Create modal */}
      <Modal
        open={showCreate}
        title="新規組織"
        description="対象リポジトリと目的を登録してください。"
        onClose={() => {
          if (!submitting) {
            setShowCreate(false)
            setCreateForm(initialForm)
          }
        }}
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
            <label className="input-label" htmlFor="org-repo-path">対象リポジトリパス</label>
            <input
              id="org-repo-path"
              className="input"
              value={createForm.target_repo_path}
              onChange={(e) => setCreateForm((c) => ({ ...c, target_repo_path: e.target.value }))}
              placeholder="/Users/name/projects/repo"
              required
            />
          </div>
          <div className="dialog-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>
              キャンセル
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <Plus size={14} />
              {submitting ? '作成中' : '作成'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit modal */}
      <Modal
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
              placeholder="/Users/name/projects/repo"
            />
          </div>
          <div className="dialog-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)}>
              キャンセル
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <Pencil size={14} />
              {submitting ? '更新中' : '保存'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete confirm modal */}
      <Modal
        open={Boolean(deleting)}
        title="組織を削除"
        description=""
        onClose={() => {
          if (!submitting) closeDeleteModal()
        }}
      >
        {deleting ? (
          deleteStep === 1 ? (
            <div className="flex flex-col gap-4">
              <p className="text-sm">
                組織「<strong>{deleting.name}</strong>」を削除しますか？
                この操作は取り消せません。
              </p>
              <div className="dialog-actions">
                <button type="button" className="btn btn-ghost" onClick={closeDeleteModal}>
                  キャンセル
                </button>
                <button type="button" className="btn btn-danger" onClick={() => setDeleteStep(2)}>
                  次へ
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-red">
                確認のため、組織名「<strong>{deleting.name}</strong>」を入力してください。
              </p>
              <input
                type="text"
                className="input"
                placeholder={deleting.name}
                value={deleteConfirmName}
                onChange={(e) => setDeleteConfirmName(e.target.value)}
                autoFocus
              />
              <div className="dialog-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setDeleteStep(1)}>
                  戻る
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleDelete}
                  disabled={submitting || deleteConfirmName !== deleting.name}
                >
                  <Trash2 size={14} />
                  {submitting ? '削除中' : '削除する'}
                </button>
              </div>
            </div>
          )
        ) : null}
      </Modal>
    </>
  )
}
