import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, CheckCircle, Sparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { CompanyManifestTable, type CompanyManifest } from '@/components/CompanyManifestTable'

/**
 * 初回ウィザード（P3.2）— 「副業ポートフォリオ自動構築」へ誘導する。
 * 会社プラグイン manifest を選んで 1 クリックで会社（Organization）を起動し、
 * 複数立ち上げてポートフォリオを作る。利用 API は既存の marketplace と同一。
 */
export function OnboardingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<1 | 2 | 3>(1)
  /**
   * manifests の 3 状態:
   *   undefined = ローディング中
   *   null      = エラー発生
   *   []        = 空
   *   [...]     = 通常リスト
   */
  const [manifests, setManifests] = useState<CompanyManifest[] | undefined | null>(undefined)
  const [installed, setInstalled] = useState<string[]>([])
  const [installing, setInstalling] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadCalled, setLoadCalled] = useState(false)

  const loadManifests = useCallback(async () => {
    setManifests(undefined)
    setLoadError(null)
    setLoadCalled(true)
    try {
      const res = await api<{ manifests: CompanyManifest[] }>(
        'GET',
        '/api/company-plugin-manifests'
      )
      setManifests(res.manifests)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'テンプレートの読み込みに失敗しました。'
      setLoadError(msg)
      setManifests(null)
      toast.error(msg)
    }
  }, [])

  // ステップ2 に初めて入ったときだけロードを起動する
  useEffect(() => {
    if (step === 2 && !loadCalled) void loadManifests()
  }, [step, loadCalled, loadManifests])

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
            <div className="card">
              <CompanyManifestTable
                manifests={manifests}
                error={loadError}
                installing={installing}
                installButtonLabel="作成"
                confirmLabel="作成する"
                showGenreDescription={false}
                heading="テンプレートから会社を立ち上げる"
                subtext="作りたい会社を選んで「作成」。複数選んでポートフォリオにできます。"
                confirmTitle={(m) => `「${m.label}」を起動しますか？`}
                confirmDescription={() => (
                  <>
                    この会社テンプレートから Organization を生成します。
                    事業部・エージェント・初期KPIが自動的に設定されます。
                  </>
                )}
                onRetry={() => void loadManifests()}
                onInstall={installCompany}
              />
            </div>

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
    </>
  )
}
