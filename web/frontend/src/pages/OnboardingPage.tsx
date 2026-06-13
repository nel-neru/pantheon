import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Building2, CheckCircle, Plus, Sparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
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

  const loadManifests = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api<{ manifests: CompanyManifest[] }>(
        'GET',
        '/api/company-plugin-manifests'
      )
      setManifests(res.manifests)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'テンプレートの読み込みに失敗しました。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (step === 2 && manifests.length === 0) void loadManifests()
  }, [step, manifests.length, loadManifests])

  const installCompany = useCallback(
    async (id: string) => {
      setInstalling(id)
      try {
        const res = await api<{ org_name: string; divisions: string[] }>(
          'POST',
          `/api/company-plugins/${encodeURIComponent(id)}/install`,
          {}
        )
        toast.success(`「${res.org_name}」を起動しました。`)
        setInstalled((prev) => (prev.includes(res.org_name) ? prev : [...prev, res.org_name]))
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '会社の作成に失敗しました。')
      } finally {
        setInstalling(null)
      }
    },
    []
  )

  return (
    <>
      <header className="page-header">
        <div className="page-title">初回セットアップ</div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {step === 1 ? (
          <div className="card">
            <div className="card-body flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <Sparkles size={18} />
                <div className="font-semibold text-lg">副業ポートフォリオを自動構築</div>
              </div>
              <p className="text-muted">
                テンプレート（会社プラグイン）を選ぶだけで、事業部・エージェント・初期KPI・人間タスクまで
                揃った「収益モデル会社」を 1 クリックで立ち上げます。複数立ち上げて、あなた専用の
                副業ポートフォリオにしましょう。公開などの最終操作は承認制なので、勝手に外部送信はしません。
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

        {step === 2 ? (
          <>
            <div className="card">
              <div className="card-body flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <Building2 size={16} />
                  <div className="font-semibold">テンプレートから会社を立ち上げる</div>
                </div>
                <p className="text-muted text-sm">
                  作りたい会社を選んで「作成」。複数選んでポートフォリオにできます。
                </p>
              </div>
            </div>

            {loading ? (
              <div className="card">
                <div className="card-body flex items-center gap-3">
                  <div className="spinner" />
                  <div className="text-muted">テンプレートを読み込み中…</div>
                </div>
              </div>
            ) : (
              <div className="card">
                <div className="card-body">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>会社</th>
                        <th>事業部</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {manifests.map((m) => (
                        <tr key={m.id}>
                          <td className="font-medium">{m.label}</td>
                          <td className="text-muted text-sm">{m.divisions.join(' / ')}</td>
                          <td className="text-right">
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              disabled={installing === m.id}
                              onClick={() => void installCompany(m.id)}
                            >
                              <Plus size={14} />
                              作成
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

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

        {step === 3 ? (
          <div className="card">
            <div className="card-body flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-green" />
                <div className="font-semibold text-lg">準備ができました</div>
              </div>
              <p className="text-muted">
                {installed.length} 社のポートフォリオを起動しました。承認インボックスで初期タスクを確認し、
                収益ページで成果を記録していきましょう。
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
    </>
  )
}
