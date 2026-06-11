import { useEffect, useRef, useState } from 'react'

import { ArrowIcon } from '@/components/Icon'
import { Exhibit, EmptyState, ErrorNote, Loading, Plate, Stat, Tag } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import type { HandoffFull, OrgSummary, Proposal } from '@/lib/types'

type OrgProposal = { org: string; proposal: Proposal }

function proposalId(p: Proposal): string {
  return String(p.proposal_id ?? p.id ?? '')
}

export function Inbox() {
  const orgs = useApi<OrgSummary[]>('/api/organizations', 45000)
  const handoffs = useApi<HandoffFull[]>('/api/handoffs', 30000)
  const [proposals, setProposals] = useState<OrgProposal[]>([])
  const [loadingProps, setLoadingProps] = useState(true)
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const reqRef = useRef(0)

  // 提案を持つ組織集合が「実際に変わったとき」だけ再フェッチする安定シグネチャ。
  // useApi の 45s ポーリングは毎回新しい配列を返すため、配列参照ではなく内容で依存する。
  const orgsSig = orgs.data
    ? orgs.data
        .filter((o) => (o.pending_proposals || 0) > 0)
        .map((o) => `${o.name}:${o.pending_proposals}`)
        .join('|')
    : null

  useEffect(() => {
    if (orgsSig === null) return // 組織一覧がまだ読み込まれていない（ローディング維持）
    const targets = (orgs.data ?? []).filter((o) => (o.pending_proposals || 0) > 0)
    if (targets.length === 0) {
      setProposals([])
      setLoadingProps(false)
      return
    }
    let cancelled = false
    const reqId = ++reqRef.current
    setLoadingProps(true)
    void (async () => {
      const results = await Promise.all(
        targets.map(async (o) => {
          try {
            const list = await api<Proposal[]>(
              'GET',
              `/api/organizations/${encodeURIComponent(o.name)}/proposals`,
            )
            return list.map((proposal) => ({ org: o.name, proposal }))
          } catch {
            return [] as OrgProposal[]
          }
        }),
      )
      // アンマウント済み or 後続リクエストが先行した場合は破棄（順序逆転による復活を防ぐ）。
      if (cancelled || reqId !== reqRef.current) return
      setProposals(results.flat())
      setLoadingProps(false)
    })()
    return () => {
      cancelled = true
    }
    // orgsSig が変わったときだけ再フェッチ（orgs.data の参照変化では走らせない）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgsSig])

  const mark = (key: string, on: boolean) =>
    setBusy((cur) => {
      const next = new Set(cur)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })

  const actOnProposal = async (org: string, pid: string, action: 'approve' | 'reject') => {
    const key = `p:${org}:${pid}`
    mark(key, true)
    try {
      await api('POST', `/api/proposals/${encodeURIComponent(org)}/${encodeURIComponent(pid)}/${action}`)
      setProposals((cur) => cur.filter((x) => !(x.org === org && proposalId(x.proposal) === pid)))
      orgs.refetch()
    } catch {
      // 失敗時は残す（UI 上の楽観更新のみ取り消し）
    } finally {
      mark(key, false)
    }
  }

  const actOnHandoff = async (id: string, action: 'approve' | 'reject') => {
    const key = `h:${id}`
    mark(key, true)
    try {
      await api(
        'POST',
        `/api/handoffs/${encodeURIComponent(id)}/${action}`,
        action === 'approve' ? { draft: true } : undefined,
      )
      handoffs.refetch()
    } catch {
      // ignore — リフェッチで整合
    } finally {
      mark(key, false)
    }
  }

  const pendingHandoffs = (handoffs.data ?? []).filter((h) => h.status === 'pending')

  return (
    <>
      <Exhibit
        index={5}
        kicker="The Review Desk"
        title={
          <>
            裁可を、<em>あなたの手で。</em>
          </>
        }
        lede="自律的に生まれた改善提案と、組織間の引き渡し。人の承認を一枚通すことで、Pantheon は暴走せず、意図に沿って前へ進みます。"
      />

      <section className="mb-12 grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-3">
        <Stat label="Proposals" value={proposals.length} tone="gold" sub="承認待ちの提案" />
        <Stat label="Handoffs" value={pendingHandoffs.length} tone="ice" sub="承認待ちの引き渡し" />
        <Stat
          label="Organizations"
          value={(orgs.data ?? []).length}
          tone="plain"
          sub="登録済みの組織"
        />
      </section>

      {/* Proposals */}
      <SectionLabel title="Improvement Proposals" note="approve / reject" />
      {loadingProps && proposals.length === 0 ? <Loading label="提案を集約" /> : null}
      {!loadingProps && proposals.length === 0 ? (
        <EmptyState title="承認待ちの提案はありません" hint="すべて捌けています" />
      ) : null}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {proposals.map(({ org, proposal }) => {
          const pid = proposalId(proposal)
          const key = `p:${org}:${pid}`
          const working = busy.has(key)
          return (
            <Plate key={key} className="flex flex-col rise">
              <div className="mb-3 flex items-center justify-between gap-3">
                <Tag tone="gold">{org}</Tag>
                <span className="mono text-faint text-[10px] tracking-wide">
                  {proposal.category || proposal.status || 'proposal'}
                </span>
              </div>
              <h3 className="serif text-xl leading-snug">{proposal.title || '(無題の提案)'}</h3>
              {proposal.description ? (
                <p className="text-dim mt-2 text-sm line-clamp-3">{proposal.description}</p>
              ) : null}
              {proposal.diff_text ? (
                <div className="mt-3 inline-flex w-fit items-center gap-2">
                  <Tag tone="ice">diff</Tag>
                  <span className="mono text-faint text-[10px]">
                    {proposal.diff_text.split('\n').length} 行の変更
                  </span>
                </div>
              ) : null}
              <div className="mt-auto flex flex-wrap items-center gap-3 pt-5">
                <button
                  type="button"
                  className="btn btn-gold"
                  disabled={working || !pid}
                  onClick={() => actOnProposal(org, pid, 'approve')}
                >
                  {working ? '…' : '承認'}
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={working || !pid}
                  onClick={() => actOnProposal(org, pid, 'reject')}
                >
                  却下
                </button>
              </div>
            </Plate>
          )
        })}
      </div>

      {/* Handoffs */}
      <div className="mt-20" />
      <SectionLabel title="Cross-Org Handoffs" note="集客 → 販売 → 収益化" />
      {handoffs.loading && !handoffs.data ? <Loading label="引き渡しを確認" /> : null}
      {handoffs.error && !handoffs.data ? <ErrorNote message={handoffs.error} /> : null}
      {handoffs.data && pendingHandoffs.length === 0 ? (
        <EmptyState title="承認待ちの引き渡しはありません" />
      ) : null}

      <div className="flex flex-col gap-4">
        {pendingHandoffs.map((h) => {
          const key = `h:${h.handoff_id}`
          const working = busy.has(key)
          return (
            <Plate key={h.handoff_id} className="rise">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="mb-2 flex items-center gap-2 mono text-[12px] tracking-wide">
                    <span className="text-gold">{h.source_org}</span>
                    <ArrowIcon size={14} />
                    <span className="text-ice">{h.target_org}</span>
                    <Tag tone="neutral">{h.kind}</Tag>
                  </div>
                  <div className="serif text-lg leading-snug">{h.title || '(無題の引き渡し)'}</div>
                  <div className="mono text-faint text-[10px] tracking-wide mt-1">
                    priority: {h.priority} · {relativeTime(h.created_at)}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    className="btn btn-gold"
                    disabled={working}
                    onClick={() => actOnHandoff(h.handoff_id, 'approve')}
                  >
                    {working ? '…' : '承認＋下書き'}
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={working}
                    onClick={() => actOnHandoff(h.handoff_id, 'reject')}
                  >
                    却下
                  </button>
                </div>
              </div>
            </Plate>
          )
        })}
      </div>
    </>
  )
}

function SectionLabel({ title, note }: { title: string; note: string }) {
  return (
    <div className="mb-6 flex items-center gap-4">
      <h2 className="serif text-3xl">{title}</h2>
      <span className="kicker">{note}</span>
      <span className="ml-2 h-px flex-1" style={{ background: 'var(--line)' }} />
    </div>
  )
}
