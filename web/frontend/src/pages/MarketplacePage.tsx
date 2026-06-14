import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Blocks, ExternalLink, Plus, RefreshCw, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { CompanyManifestTable, type CompanyManifest } from '@/components/CompanyManifestTable'
import { priorityBadge, priorityLabel } from '@/lib/labels'

type DivisionPlugin = {
  id: string
  label: string
  category: string
  description: string
}

type BusinessProposal = {
  id: string
  org_name: string
  title: string
  priority: string
  expected_impact: string
  route: string
}

type OrgRow = { id: string; name: string }

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  destructive?: boolean
  run: () => Promise<void>
}

export function MarketplacePage() {
  const navigate = useNavigate()
  const [manifests, setManifests] = useState<CompanyManifest[] | undefined | null>(undefined)
  const [division, setDivision] = useState<DivisionPlugin[]>([])
  const [orgs, setOrgs] = useState<OrgRow[]>([])
  const [bizProposals, setBizProposals] = useState<BusinessProposal[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [manifestError, setManifestError] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const initialLoadDone = useRef(false)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [man, div, orgList, biz] = await Promise.all([
        api<{ manifests: CompanyManifest[] }>('GET', '/api/company-plugin-manifests'),
        api<{ plugins: DivisionPlugin[] }>('GET', '/api/division-plugins'),
        api<OrgRow[]>('GET', '/api/organizations'),
        api<{ items: BusinessProposal[] }>('GET', '/api/hq/business-proposals'),
      ])
      setManifests(man.manifests ?? [])
      setManifestError(null)
      setDivision(div.plugins ?? [])
      setOrgs(Array.isArray(orgList) ? orgList : [])
      setBizProposals(biz.items ?? [])
      if (Array.isArray(orgList) && orgList.length > 0)
        setSelectedOrg((prev) => prev || orgList[0].name)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'マーケットプレイスの読み込みに失敗しました。'
      setError(message)
      setManifests(null)
      setManifestError(message)
      toast.error(message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!initialLoadDone.current) {
      initialLoadDone.current = true
      void load(false)
    }
  }, [load])

  const handleRefresh = useCallback(() => {
    setRefreshing(true)
    void load(true)
  }, [load])

  const scanBusiness = useCallback(async () => {
    setScanning(true)
    try {
      const res = await api<{ proposals: number; reason?: string }>(
        'POST',
        '/api/hq/business-proposals/scan',
        { min_score: 7.0 }
      )
      if (res.reason === 'no_org') {
        toast.error('受け手の組織がありません。先に会社を作成してください。')
      } else {
        const n = res.proposals ?? 0
        toast.success(
          n > 0
            ? `トレンドから新規会社候補を ${n} 件起票しました。`
            : 'トレンドから新しい候補は見つかりませんでした。'
        )
      }
      await load(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'スキャンに失敗しました。')
    } finally {
      setScanning(false)
    }
  }, [load])

  const scanUntapped = useCallback(async () => {
    setScanning(true)
    try {
      const res = await api<{ proposals: number; reason?: string }>(
        'POST',
        '/api/hq/untapped-genres/scan',
        { min_score: 7.0 }
      )
      if (res.reason === 'no_org') {
        toast.error('受け手の組織がありません。先に会社を作成してください。')
      } else {
        const n = res.proposals ?? 0
        toast.success(
          n > 0
            ? `未開拓ジャンルから新会社候補を ${n} 件起票しました。`
            : '未開拓ジャンルから新しい候補は見つかりませんでした。'
        )
      }
      await load(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'スキャンに失敗しました。')
    } finally {
      setScanning(false)
    }
  }, [load])

  const installCompanyConfirmed = useCallback(
    async (manifest: CompanyManifest) => {
      setInstalling(manifest.id)
      try {
        const res = await api<{ org_name: string; divisions: string[] }>(
          'POST',
          `/api/company-plugins/${encodeURIComponent(manifest.id)}/install`,
          {}
        )
        toast.success(`会社「${res.org_name}」を起動しました（${res.divisions.length} 事業部）。`)
        await load(true)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '会社の作成に失敗しました。')
        throw err
      } finally {
        setInstalling(null)
      }
    },
    [load]
  )

  const installDivisionConfirmed = useCallback(
    async (pluginId: string, orgName: string, pluginLabel: string) => {
      setInstalling(pluginId)
      try {
        const res = await api<{ division: { name: string } }>(
          'POST',
          `/api/organizations/${encodeURIComponent(orgName)}/divisions`,
          { plugin_id: pluginId }
        )
        toast.success(`${orgName} に「${res.division.name ?? pluginLabel}」を追加しました。`)
        await load(true) // P0 fix: 成功後に必ず画面を更新する
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '追加に失敗しました。')
        throw err
      } finally {
        setInstalling(null)
      }
    },
    [load]
  )

  const requestInstallDivision = useCallback(
    (p: DivisionPlugin) => {
      if (!selectedOrg) {
        toast.error('追加先の組織を選択してください。')
        return
      }
      const orgName = selectedOrg
      setConfirm({
        title: `「${p.label}」を ${orgName} に追加しますか？`,
        description: (
          <>
            <span className="text-sm text-fg2">{p.description}</span>
            <br />
            <span className="text-sm text-fg2">追加先: {orgName}</span>
          </>
        ),
        confirmLabel: '追加する',
        destructive: false,
        run: () => installDivisionConfirmed(p.id, orgName, p.label),
      })
    },
    [selectedOrg, installDivisionConfirmed]
  )

  const isBusy = installing !== null || scanning

  return (
    <>
      <header className="page-header">
        <div className="page-title">マーケットプレイス</div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleRefresh}
            disabled={refreshing || loading}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : undefined} />
            {refreshing ? '更新中…' : '更新'}
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">プラグインを読み込み中…</div>
            </div>
          </div>
        ) : error ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>読み込みに失敗しました</h3>
                <p>{error}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void load(false)}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* ── Card 1: Company Manifests ── */}
            <div className="card">
              <CompanyManifestTable
                manifests={manifests}
                error={manifestError}
                installing={installing}
                busy={scanning}
                installButtonLabel="この会社を作成"
                confirmLabel="この会社を作成"
                showGenreDescription={true}
                heading="会社プラグイン（テンプレートから1クリックで会社を起動）"
                subtext="manifest を選んで「この会社を作成」すると、事業部・Agent・初期KPI・人間タスクまで揃った収益モデル会社（Organization）が即座に立ち上がります。"
                confirmTitle={(m) => `「${m.label}」を作成しますか？`}
                confirmDescription={(m) => (
                  <>
                    事業部・Agent・初期KPI・人間タスクまで含む会社を一括生成します。
                    {m.divisions.length > 0 && (
                      <>
                        <br />
                        <span className="text-sm text-fg2">作成される事業部: {m.divisions.join('、')}</span>
                      </>
                    )}
                    {m.description && (
                      <>
                        <br />
                        <span className="text-sm text-fg2">{m.description}</span>
                      </>
                    )}
                  </>
                )}
                onRetry={() => void load(false)}
                onInstall={installCompanyConfirmed}
              />
            </div>

            {/* ── Card 2: Business Proposals ── */}
            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} />
                    <div className="font-semibold">新規会社候補（トレンド発・要承認）</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={scanning || isBusy}
                      onClick={() => void scanBusiness()}
                      title="直近のトレンドをスコアリングして新会社候補を自動起票します"
                    >
                      <Sparkles size={14} />
                      {scanning ? 'スキャン中…' : 'トレンドからスキャン'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={scanning || isBusy}
                      onClick={() => void scanUntapped()}
                      title="既存組織がカバーしていない未開拓ジャンルを探して候補を起票します"
                    >
                      <Sparkles size={14} />
                      {scanning ? 'スキャン中…' : '未開拓ジャンルをスキャン'}
                    </button>
                  </div>
                </div>
                <p className="text-muted text-sm">
                  高スコアトレンドから「新しい収益モデル会社」候補を自動起票します（自動採用はせず、
                  承認インボックスで人間が承認して初めて会社化）。
                  <br />
                  <span className="text-xs">
                    トレンドからスキャン: 直近のトレンドを起点に候補生成 ／
                    未開拓ジャンルをスキャン: 現組織がカバーしていないジャンルを探して候補生成。
                  </span>
                </p>
                {bizProposals.length === 0 ? (
                  <div className="text-muted text-sm">
                    候補はまだありません。上のスキャンボタンで生成できます。
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>候補</th>
                        <th>優先度</th>
                        <th>期待インパクト</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {bizProposals.map((b) => (
                        <tr key={b.id}>
                          <td className="font-medium">{b.title}</td>
                          <td>
                            <span className={`badge ${priorityBadge(b.priority)}`}>
                              {priorityLabel(b.priority)}
                            </span>
                          </td>
                          <td className="text-muted text-sm">{b.expected_impact}</td>
                          <td className="text-right">
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => navigate('/inbox')}
                              title="承認インボックスで承認して会社化できます"
                            >
                              <ExternalLink size={12} />
                              承認インボックスで開く
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* ── Card 3: Division Plugins ── */}
            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <Blocks size={16} />
                    <div className="font-semibold">事業部プラグイン（既存の会社に追加）</div>
                  </div>
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <span>追加先の組織</span>
                    <select
                      className="select"
                      value={selectedOrg}
                      onChange={(e) => setSelectedOrg(e.target.value)}
                      disabled={orgs.length === 0}
                    >
                      {orgs.length === 0 ? (
                        <option value="">（組織がありません）</option>
                      ) : (
                        orgs.map((o) => (
                          <option key={o.id} value={o.name}>
                            {o.name}
                          </option>
                        ))
                      )}
                    </select>
                  </label>
                </div>
                {orgs.length === 0 && (
                  <p className="text-muted text-sm">
                    事業部を追加するには、先に上の「会社プラグイン」からOrganizationを作成してください。
                  </p>
                )}
                {division.length === 0 ? (
                  <div className="empty-state py-6">
                    <Blocks className="empty-state-icon" size={24} />
                    <p className="text-muted text-sm">事業部プラグインがありません。</p>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>事業部</th>
                        <th>カテゴリ</th>
                        <th>説明</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {division.map((p) => (
                        <tr key={p.id}>
                          <td className="font-medium">{p.label}</td>
                          <td>
                            <span className="badge badge-neutral">{p.category}</span>
                          </td>
                          <td className="text-muted text-sm">{p.description}</td>
                          <td className="text-right">
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              disabled={!selectedOrg || isBusy}
                              onClick={() => requestInstallDivision(p)}
                            >
                              <Plus size={14} />
                              {installing === p.id ? '追加中…' : '追加'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel}
        destructive={confirm?.destructive ?? true}
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </>
  )
}
