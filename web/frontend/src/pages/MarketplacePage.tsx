import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Blocks, Building2, Plus, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type CompanyManifest = {
  id: string
  label: string
  genre?: string
  description?: string
  divisions: string[]
  initial_kpis?: string[]
}

type DivisionPlugin = {
  id: string
  label: string
  category: string
  description: string
}

type OrgRow = { id: string; name: string }

export function MarketplacePage() {
  const [manifests, setManifests] = useState<CompanyManifest[]>([])
  const [division, setDivision] = useState<DivisionPlugin[]>([])
  const [orgs, setOrgs] = useState<OrgRow[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [man, div, orgList] = await Promise.all([
        api<{ manifests: CompanyManifest[] }>('GET', '/api/company-plugin-manifests'),
        api<{ plugins: DivisionPlugin[] }>('GET', '/api/division-plugins'),
        api<OrgRow[]>('GET', '/api/organizations'),
      ])
      setManifests(man.manifests)
      setDivision(div.plugins)
      setOrgs(orgList)
      if (orgList.length > 0) setSelectedOrg((prev) => prev || orgList[0].name)
      setError(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'マーケットプレイスの読み込みに失敗しました。'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const installCompany = useCallback(
    async (pluginId: string) => {
      setInstalling(pluginId)
      try {
        const res = await api<{ org_name: string; divisions: string[] }>(
          'POST',
          `/api/company-plugins/${encodeURIComponent(pluginId)}/install`,
          {}
        )
        toast.success(`会社「${res.org_name}」を起動しました（${res.divisions.length} 事業部）。`)
        await load()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '会社の作成に失敗しました。')
      } finally {
        setInstalling(null)
      }
    },
    [load]
  )

  const installDivision = useCallback(
    async (pluginId: string) => {
      if (!selectedOrg) {
        toast.error('追加先の組織を選択してください。')
        return
      }
      setInstalling(pluginId)
      try {
        const res = await api<{ division: { name: string } }>(
          'POST',
          `/api/organizations/${encodeURIComponent(selectedOrg)}/divisions`,
          { plugin_id: pluginId }
        )
        toast.success(`${selectedOrg} に「${res.division.name}」を追加しました。`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '追加に失敗しました。')
      } finally {
        setInstalling(null)
      }
    },
    [selectedOrg]
  )

  return (
    <>
      <header className="page-header">
        <div className="page-title">マーケットプレイス</div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            <RefreshCw size={14} />
            更新
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
                <button type="button" className="btn btn-secondary" onClick={() => void load()}>
                  再試行
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="card">
              <div className="card-body flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <Building2 size={16} />
                  <div className="font-semibold">会社プラグイン（テンプレートから1クリックで会社を起動）</div>
                </div>
                <p className="text-muted text-sm">
                  manifest を選んで「この会社を作成」すると、事業部・Agent・初期KPI・人間タスクまで揃った
                  収益モデル会社（Organization）が即座に立ち上がります。
                </p>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>会社</th>
                      <th>事業部</th>
                      <th>初期KPI</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {manifests.map((m) => (
                      <tr key={m.id}>
                        <td className="font-medium">{m.label}</td>
                        <td className="text-muted text-sm">{m.divisions.join(' / ')}</td>
                        <td className="text-muted text-sm">{(m.initial_kpis ?? []).join(' / ')}</td>
                        <td className="text-right">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            disabled={installing === m.id}
                            onClick={() => void installCompany(m.id)}
                          >
                            <Plus size={14} />
                            この会社を作成
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <Blocks size={16} />
                    <div className="font-semibold">事業部プラグイン（既存の会社に追加）</div>
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    <span className="text-muted">追加先</span>
                    <select
                      className="select"
                      value={selectedOrg}
                      onChange={(e) => setSelectedOrg(e.target.value)}
                    >
                      {orgs.length === 0 ? <option value="">（組織がありません）</option> : null}
                      {orgs.map((o) => (
                        <option key={o.id} value={o.name}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
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
                            disabled={!selectedOrg || installing === p.id}
                            onClick={() => void installDivision(p.id)}
                          >
                            <Plus size={14} />
                            追加
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
