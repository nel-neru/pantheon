import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, FileDiff, Lightbulb, MessageSquareText, XCircle } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { CoreImprovePanel } from '@/components/CoreImprovePanel'
import { api } from '@/lib/api'
import { priorityBadge } from '@/lib/utils'

type Organization = {
  name: string
}

type Proposal = {
  id: string | number
  title: string
  description: string
  priority: string
  category: string
  file_path: string
  status: string
  diff_text?: string
  approval_notes?: string
}

const activeProposalStatuses = ['proposed', 'pending', 'in_progress']

function truncateText(value: string, max = 200) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

function proposalStatusLabel(status: string) {
  if (status === 'approved' || status === 'done') return '承認済み'
  if (status === 'rejected') return '却下済み'
  if (status === 'in_progress') return '実行中'
  return '未処理'
}

function DiffPreview({ diffText }: { diffText: string }) {
  if (!diffText.trim()) {
    return <div className="text-sm text-muted">この提案にはコード差分プレビューがありません。</div>
  }

  return (
    <pre className="progress-log" style={{ whiteSpace: 'pre-wrap' }}>
      {diffText.split('\n').map((line, index) => {
        const style = line.startsWith('+')
          ? { color: '#7ee787', background: 'rgba(46, 160, 67, 0.14)' }
          : line.startsWith('-')
            ? { color: '#ff7b72', background: 'rgba(248, 81, 73, 0.12)' }
            : line.startsWith('@@')
              ? { color: '#79c0ff' }
              : undefined
        return (
          <div key={`${index}-${line}`} style={style}>
            {line}
          </div>
        )
      })}
    </pre>
  )
}

export function ProposalsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState<string | number | null>(null)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [organizationsError, setOrganizationsError] = useState<string | null>(null)
  const [proposalsError, setProposalsError] = useState<string | null>(null)
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({})
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const loadOrganizations = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<Organization[]>('GET', '/api/organizations')
      setOrganizations(data)
      setOrganizationsError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '組織の読み込みに失敗しました。'
      setOrganizations([])
      setSelectedOrg('')
      setProposals([])
      setOrganizationsError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadProposals = useCallback(async (orgName: string) => {
    setLoading(true)
    try {
      const data = await api<Proposal[]>(
        'GET',
        `/api/organizations/${encodeURIComponent(orgName)}/proposals`,
      )
      setProposals(data)
      setApprovalNotes(
        Object.fromEntries(data.map((proposal) => [String(proposal.id), proposal.approval_notes ?? '']))
      )
      setSelectedIds([])
      setProposalsError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '提案の読み込みに失敗しました。'
      setProposals([])
      setApprovalNotes({})
      setSelectedIds([])
      setProposalsError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadOrganizations()
  }, [loadOrganizations])

  useEffect(() => {
    if (organizations.length === 0) return

    const requested = searchParams.get('org')
    const fallback = organizations[0]?.name ?? ''
    const nextOrg = organizations.some((org) => org.name === requested) ? requested ?? fallback : fallback

    setSelectedOrg((current) => current || nextOrg)
  }, [organizations, searchParams])

  useEffect(() => {
    if (!selectedOrg) return
    setSearchParams({ org: selectedOrg }, { replace: true })
    void loadProposals(selectedOrg)
  }, [loadProposals, selectedOrg, setSearchParams])

  const categories = useMemo(() => {
    const cats = Array.from(new Set(proposals.map((proposal) => proposal.category).filter(Boolean)))
    return cats.sort()
  }, [proposals])

  const filteredProposals = useMemo(() => {
    return proposals.filter((proposal) => {
      const statusMatch =
        statusFilter === 'all'
          ? true
          : statusFilter === 'pending'
            ? activeProposalStatuses.includes(proposal.status)
            : proposal.status === statusFilter
      const categoryMatch = categoryFilter === 'all' || proposal.category === categoryFilter
      return statusMatch && categoryMatch
    })
  }, [proposals, statusFilter, categoryFilter])
  const selectableProposalIds = useMemo(
    () => filteredProposals.filter((proposal) => activeProposalStatuses.includes(proposal.status)).map((proposal) => String(proposal.id)),
    [filteredProposals],
  )
  const allSelected = selectableProposalIds.length > 0 && selectableProposalIds.every((id) => selectedIds.includes(id))

  const toggleSelection = (proposalId: string) => {
    setSelectedIds((current) =>
      current.includes(proposalId) ? current.filter((id) => id !== proposalId) : [...current, proposalId],
    )
  }

  const handleSelectAll = () => {
    setSelectedIds((current) => (allSelected ? current.filter((id) => !selectableProposalIds.includes(id)) : Array.from(new Set([...current, ...selectableProposalIds]))))
  }

  const handleProposalAction = async (proposal: Proposal, action: 'approve' | 'reject') => {
    const notes = approvalNotes[String(proposal.id)] ?? ''
    setActionId(proposal.id)
    try {
      const result = await api<{ status?: string; approval_notes?: string }>(
        'POST',
        `/api/proposals/${encodeURIComponent(selectedOrg)}/${proposal.id}/${action}`,
        action === 'approve' ? { approval_notes: notes } : undefined,
      )
      setProposals((current) =>
        current.map((item) =>
          item.id === proposal.id
            ? {
                ...item,
                status: result.status ?? (action === 'approve' ? 'done' : 'rejected'),
                approval_notes: result.approval_notes ?? notes,
              }
            : item,
        ),
      )
      setSelectedIds((current) => current.filter((id) => id !== String(proposal.id)))
      toast.success(action === 'approve' ? '提案を承認しました。' : '提案を却下しました。')
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : action === 'approve'
            ? '提案の承認に失敗しました。'
            : '提案の却下に失敗しました。',
      )
    } finally {
      setActionId(null)
    }
  }

  const handleBatchAction = async (action: 'approve' | 'reject') => {
    if (selectedIds.length === 0) return
    setActionId(action)
    try {
      const result = await api<{
        results: { proposal_id: string; ok: boolean; status?: string }[]
      }>('POST', `/api/proposals/${encodeURIComponent(selectedOrg)}/batch`, {
        proposal_ids: selectedIds,
        action,
      })
      const updatedIds = result.results.filter((item) => item.ok).map((item) => item.proposal_id)
      setProposals((current) =>
        current.map((proposal) =>
          updatedIds.includes(String(proposal.id))
            ? { ...proposal, status: action === 'approve' ? 'done' : 'rejected' }
            : proposal,
        ),
      )
      setSelectedIds([])
      toast.success(action === 'approve' ? `${updatedIds.length} 件の提案を承認しました。` : `${updatedIds.length} 件の提案を却下しました。`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '提案の一括操作に失敗しました。')
    } finally {
      setActionId(null)
    }
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">改善提案</div>
        <div className="page-actions">
          <select
            className="select"
            value={selectedOrg}
            onChange={(event) => setSelectedOrg(event.target.value)}
            disabled={organizations.length === 0}
          >
            {organizations.map((org) => (
              <option key={org.name} value={org.name}>
                {org.name}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="all">すべてのステータス</option>
            <option value="pending">未対応</option>
            <option value="in_progress">実行中</option>
            <option value="done">承認済み</option>
            <option value="rejected">却下済み</option>
          </select>
          <select
            className="select"
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
          >
            <option value="all">全カテゴリ</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <CoreImprovePanel
          onProposed={(orgName) => {
            setSelectedOrg(orgName)
            void loadOrganizations()
            void loadProposals(orgName)
          }}
        />

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">提案を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && organizationsError ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>組織の読み込みに失敗しました</h3>
                <p>{organizationsError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadOrganizations()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !organizationsError && organizations.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <Lightbulb className="empty-state-icon" size={28} />
                <h3>改善提案がありません</h3>
                <p>組織を作成して分析を実行すると改善提案が生成されます。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !organizationsError && organizations.length > 0 && proposalsError ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>提案の読み込みに失敗しました</h3>
                <p>{proposalsError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadProposals(selectedOrg)}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !organizationsError && !proposalsError && organizations.length > 0 && filteredProposals.length === 0 ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <Lightbulb className="empty-state-icon" size={28} />
                <h3>一致する提案がありません</h3>
                <p>ステータスフィルタを変更するか、新しい分析を実行してください。</p>
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !organizationsError && !proposalsError && filteredProposals.length > 0 ? (
          <div className="proposal-batch-bar">
            <label className="proposal-select-all">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={handleSelectAll}
                aria-label="表示中の提案をすべて選択"
              />
              <span>Select All</span>
            </label>
            <span className="text-sm text-muted">{selectedIds.length} 件を選択中</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn btn-secondary btn-sm text-green"
                onClick={() => void handleBatchAction('approve')}
                disabled={selectedIds.length === 0 || actionId === 'approve'}
              >
                <CheckCircle size={14} />
                一括承認
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => void handleBatchAction('reject')}
                disabled={selectedIds.length === 0 || actionId === 'reject'}
              >
                <XCircle size={14} />
                一括却下
              </button>
            </div>
          </div>
        ) : null}

        {!loading && !organizationsError && !proposalsError && filteredProposals.length > 0
          ? filteredProposals.map((proposal) => (
              <div key={proposal.id} className="proposal-card">
                <div className="proposal-header">
                  <label className="proposal-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(String(proposal.id))}
                      onChange={() => toggleSelection(String(proposal.id))}
                      disabled={!activeProposalStatuses.includes(proposal.status)}
                      aria-label={`${proposal.title} を選択`}
                    />
                  </label>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <div className="font-semibold truncate">{proposal.title}</div>
                      <span className={`badge ${priorityBadge(proposal.priority)}`}>{proposal.priority}</span>
                      <span className="badge badge-neutral">{proposal.category}</span>
                      <span
                        className={`badge ${
                          proposal.status === 'approved' || proposal.status === 'done'
                            ? 'badge-green'
                            : proposal.status === 'rejected'
                              ? 'badge-red'
                              : proposal.status === 'in_progress'
                                ? 'badge-yellow'
                                : 'badge-blue'
                        }`}
                      >
                        {proposalStatusLabel(proposal.status)}
                      </span>
                    </div>
                    <div className="text-sm text-fg2">{truncateText(proposal.description)}</div>
                  </div>
                </div>
                <div className="proposal-body flex flex-col gap-4">
                  <div>
                    <div className="metric-label">ファイルパス</div>
                    <div className="mono text-sm text-fg2 mt-2">{proposal.file_path}</div>
                  </div>

                  <details open={Boolean(proposal.diff_text)}>
                    <summary className="flex items-center gap-2 cursor-pointer font-medium">
                      <FileDiff size={14} />
                      差分プレビュー
                    </summary>
                    <div className="mt-3">
                      <DiffPreview diffText={proposal.diff_text ?? ''} />
                    </div>
                  </details>

                  <div className="input-group">
                    <label className="input-label" htmlFor={`approval-notes-${proposal.id}`}>
                      <span className="inline-flex items-center gap-2">
                        <MessageSquareText size={14} />
                        承認メモ
                      </span>
                    </label>
                    <textarea
                      id={`approval-notes-${proposal.id}`}
                      className="textarea"
                      value={approvalNotes[String(proposal.id)] ?? ''}
                      onChange={(event) =>
                        setApprovalNotes((current) => ({
                          ...current,
                          [String(proposal.id)]: event.target.value,
                        }))
                      }
                      placeholder="承認理由やフォローアップ事項を記録できます"
                      rows={3}
                    />
                  </div>
                </div>
                <div className="proposal-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm text-green"
                    onClick={() => void handleProposalAction(proposal, 'approve')}
                    disabled={actionId === proposal.id || proposal.status === 'approved' || proposal.status === 'done'}
                  >
                    <CheckCircle size={14} />
                    {actionId === proposal.id ? '更新中' : '承認'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => void handleProposalAction(proposal, 'reject')}
                    disabled={actionId === proposal.id || proposal.status === 'rejected'}
                  >
                    <XCircle size={14} />
                    {actionId === proposal.id ? '更新中' : '却下'}
                  </button>
                </div>
              </div>
            ))
          : null}
      </div>
    </>
  )
}
