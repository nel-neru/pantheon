import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ArrowRight, Building2, CheckCircle, PackageOpen, Plus, Sparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'

type CompanyManifest = {
  id: string
  label: string
  genre?: string
  description?: string
  divisions: string[]
  initial_kpis?: string[]
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

/**
 * 初回ウィザード（P3.2）— 「副業ポートフォリオ自動構築」へ誘導する。
 * 会社プラグイン manifest を選んで 1 クリックで会社（Organization）を起動し、
 * 複数立ち上げてポートフォリオを作る。利用 API は既存の marketplace と同一。
 */
export function OnboardingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [manifests, setManifests] = useState<CompanyManifest[]>([])
  const [installed, setInstalled] = useState<string[]>([])
  const [installing, setInstalling] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

  const loadManifests = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await api<{ manifests: CompanyManifest[] }>(
        'GET',
        '/api/company-plugin-manifests'
      )
      setManifests(res.manifests)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'テンプレートの読み込みに失敗しました。'
      setLoadError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (step === 2 && manifests.length === 0 && loadError === null) void loadManifests()
  }, [step, manifests.length, loadError, loadManifests])

  const installCompany = useCallback(async (manifest: CompanyManifest): Promise<void> => {
    setInstalling(manifest.id)
    try {
      const res = await api<{ org_name: string; divisions: string[] }>(
        'POST',
        `/api/company-plugins/${encodeURIComponent(manifest.id)}/install`,
        {}
      )
      toast.success(`「${res.org_name}」を起動しました。`)
      setInstalled((prev) => (prev.includes(res.org_name) ? prev : [...prev, res.org_name]))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '会社の作成に失敗しました。')
      throw err
    } finally {
      setInstalling(null)
    }
  }, [])

  const requestInstall = (manifest: CompanyManifest) => {
    setConfirm({
      title: `「${manifest.label}」を起動しますか？`,
      description: (
        <>
          この会社テンプレートから Organization を生成します。
          事業部・エージェント・初期KPIが自動的に設定されます。
        </>
      ),
      confirmLabel: '作成する',
      run: () => installCompany(manifest),
    })
  }

  const STEP_LABELS: Record<1 | 2 | 3, string> = {
    1: 'はじめに',
    2: 'テンプレを選ぶ',
    3: '完了',
  }

  return (
    <>
      <header className="page-header">
        <div>
          <div className="page-title">初回セットアップ</div>
          <div className="text-sm text-muted">
            ステップ {step} / 3 — {STEP_LABELS[step]}
          </div>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {/* Step 1: Introduction */}
        {step === 1 ? (
          <div className="card">
            <div className="card-body flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <Sparkles size={18} />
                <div className="font-semibold text-lg">副業ポートフォリオを自動構築</div>
              </div>
              <p className="text-muted" id="step1-description">
                テンプレートを選ぶだけで、事業部・エージェント・初期KPIが揃った「収益モデル会社」を
                1クリックで立ち上げます。複数立ち上げてあなた専用の副業ポートフォリオにしましょう。
                公開などの最終操作は承認制なので、勝手に外部送信はしません。
              </p>
              <div>
                <button type="button" className="btn btn-primary" onClick={() => setStep(2)}>
                  始める
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Step 2: Template selection */}
        {step === 2 ? (
          <>
            {/* Loading state */}
            {loading ? (
              <div className="card">
                <div className="card-body">
                  <div className="flex items-center gap-2 mb-3">
                    <Building2 size={16} />
                    <div className="font-semibold">テンプレートから会社を立ち上げる</div>
                  </div>
                  <p className="text-muted text-sm mb-4">
                    作りたい会社を選んで「作成」。複数選んでポートフォリオにできます。
                  </p>
                  <div className="flex items-center gap-3">
                    <div className="spinner" />
                    <div className="text-muted">テンプレートを読み込み中…</div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Error state */}
            {!loading && loadError ? (
              <div className="card">
                <div className="card-body">
                  <div className="flex items-center gap-2 mb-3">
                    <Building2 size={16} />
                    <div className="font-semibold">テンプレートから会社を立ち上げる</div>
                  </div>
                  <div className="empty-state">
                    <PackageOpen className="empty-state-icon" size={28} />
                    <h3>テンプレートの読み込みに失敗しました</h3>
                    <p>{loadError}</p>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => void loadManifests()}
                    >
                      再試行
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Table */}
            {!loading && !loadError ? (
              <div className="card" id="manifests-table">
                <div className="card-body">
                  <div className="flex items-center gap-2 mb-1">
                    <Building2 size={16} />
                    <div className="font-semibold">テンプレートから会社を立ち上げる</div>
                  </div>
                  <p className="text-muted text-sm mb-4">
                    作りたい会社を選んで「作成」。複数選んでポートフォリオにできます。
                  </p>

                  {manifests.length === 0 ? (
                    <div className="empty-state">
                      <PackageOpen className="empty-state-icon" size={28} />
                      <h3>テンプレートがありません</h3>
                      <p>利用可能な会社テンプレートが見つかりませんでした。</p>
                    </div>
                  ) : (
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
                        {manifests.map((m) => {
                          const busy = installing === m.id
                          return (
                            <tr key={m.id}>
                              <td className="font-medium">{m.label}</td>
                              <td className="text-muted text-sm">{m.divisions.join(' / ')}</td>
                              <td className="text-muted text-sm">
                                {m.initial_kpis && m.initial_kpis.length > 0
                                  ? m.initial_kpis.join(' / ')
                                  : '—'}
                              </td>
                              <td className="text-right">
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  disabled={busy || installing !== null}
                                  onClick={() => requestInstall(m)}
                                >
                                  {busy ? (
                                    <>
                                      <div className="spinner" />
                                      作成中…
                                    </>
                                  ) : (
                                    <>
                                      <Plus size={14} />
                                      作成
                                    </>
                                  )}
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ) : null}

            {/* Installed list */}
            {installed.length > 0 ? (
              <div className="card">
                <div className="card-body flex flex-col gap-2">
                  <div className="font-semibold">作成済み（{installed.length} 社）</div>
                  {installed.map((name) => (
                    <div key={name} className="flex items-center gap-2 text-sm">
                      <CheckCircle size={14} className="text-green" />
                      {name}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={installed.length === 0}
                onClick={() => setStep(3)}
              >
                完了する
                <ArrowRight size={14} />
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => navigate('/dashboard')}>
                スキップ
              </button>
            </div>
          </>
        ) : null}

        {/* Step 3: Completion */}
        {step === 3 ? (
          <div className="card">
            <div className="card-body flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-green" />
                <div className="font-semibold text-lg">準備ができました</div>
              </div>
              <p className="text-muted" id="step3-description">
                {installed.length} 社のポートフォリオを起動しました。承認インボックスで初期タスクを確認し、
                組織ページで事業部とエージェントの状況を確認しましょう。
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <Link to="/dashboard" className="btn btn-primary">
                  ダッシュボードへ
                </Link>
                <Link to="/orgs" className="btn btn-secondary">
                  組織を見る
                </Link>
                <Link to="/inbox" className="btn btn-secondary">
                  承認インボックス
                </Link>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel}
        destructive={false}
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </>
  )
}
