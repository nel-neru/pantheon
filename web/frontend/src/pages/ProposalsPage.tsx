import { useCallback, useEffect, useMemo, useState } from 'react'
import { CheckCircle, Lightbulb, XCircle } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

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

export function ProposalsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState<string | number | null>(null)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [categoryFilter, setCategoryFilter] = useState('all')

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

  const loadProposals = useCallback(async (orgName: string) => {
    setLoading(true)
    try {
      const data = await api<Proposal[]>(
        'GET',
        `/api/organizations/${encodeURIComponent(orgName)}/proposals`,
      )
      setProposals(data)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '提案の読み込みに失敗しました。')
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

  const handleProposalAction = async (proposal: Proposal, action: 'approve' | 'reject') => {
    setActionId(proposal.id)
    try {
      const result = await api<{ status?: string }>(
        'POST',
        `/api/proposals/${encodeURIComponent(selectedOrg)}/${proposal.id}/${action}`,
      )
      setProposals((current) =>
        current.map((item) =>
          item.id === proposal.id
            ? { ...item, status: result.status ?? (action === 'approve' ? 'done' : 'rejected') }
            : item,
        ),
      )
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
        {organizations.length === 0 && !loading ? (
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

        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">提案を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading && organizations.length > 0 && filteredProposals.length === 0 ? (
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

        {!loading && filteredProposals.length > 0
          ? filteredProposals.map((proposal) => (
              <div key={proposal.id} className="proposal-card">
                <div className="proposal-header">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
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
                <div className="proposal-body">
                  <div className="metric-label">ファイルパス</div>
                  <div className="mono text-sm text-fg2 mt-2">{proposal.file_path}</div>
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
