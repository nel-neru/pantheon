import { useCallback, useEffect, useState } from 'react'
import { Save, Terminal } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { formatBytes } from '@/lib/utils'

type SettingsData = {
  llm_model: string
  daemon_interval: number
  daemon_max_files: number
  model_configurations: Record<string, unknown>
  prompt_templates: Record<string, string>
  policy_rules: Record<string, unknown>
  settings_file: string
  has_llm: boolean
}

type ModelsResponse = {
  provider: string
  models: string[]
  source: string
}

type RuntimeStatus = {
  claude: { available: boolean; binary?: string | null }
  wmux: { running: boolean; state: string }
  driver: string
}

type StorageEntry = {
  label: string
  path: string
  exists: boolean
  file_count: number
  size_bytes: number
  last_modified: string | null
}

type StorageInfo = {
  platform_home: string
  note: string
  storage: Record<string, StorageEntry>
}

const DEFAULT_SETTINGS_DATA: SettingsData = {
  llm_model: 'claude-opus-4-8',
  daemon_interval: 3600,
  daemon_max_files: 10,
  model_configurations: { default: { temperature: 0.2, max_tokens: 4096, fallback_model: '' } },
  prompt_templates: { analysis: 'Analyze the repository and propose improvements.' },
  policy_rules: { auto_approve: { conditions: {} }, human_required: { conditions: {} }, auto_reject: { conditions: {} } },
  settings_file: '—',
  has_llm: false,
}

function prettyJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}

function parseJsonObject(label: string, text: string) {
  try {
    const parsed = JSON.parse(text)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(`${label} は JSON オブジェクトで指定してください。`)
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    if (error instanceof Error) throw error
    throw new Error(`${label} の解析に失敗しました。`)
  }
}

function wmuxLabel(state: string) {
  if (state === 'connected') return 'wmux 接続中'
  if (state === 'awaiting-approval') return 'wmux 承認待ち（wmux ウィンドウで pantheon を承認）'
  if (state === 'not-running') return 'wmux 未起動'
  return 'wmux エラー'
}

export function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null)
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)

  const [model, setModel] = useState(DEFAULT_SETTINGS_DATA.llm_model)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [daemonInterval, setDaemonInterval] = useState(3600)
  const [daemonMaxFiles, setDaemonMaxFiles] = useState(10)
  const [modelConfigurationsText, setModelConfigurationsText] = useState(prettyJson(DEFAULT_SETTINGS_DATA.model_configurations))
  const [promptTemplatesText, setPromptTemplatesText] = useState(prettyJson(DEFAULT_SETTINGS_DATA.prompt_templates as Record<string, unknown>))
  const [policyRulesText, setPolicyRulesText] = useState(prettyJson(DEFAULT_SETTINGS_DATA.policy_rules))

  const load = useCallback(async () => {
    setLoading(true)
    const [settingsResult, storageResult, runtimeResult, modelsResult] = await Promise.allSettled([
      api<SettingsData>('GET', '/api/settings'),
      api<StorageInfo>('GET', '/api/storage/info'),
      api<RuntimeStatus>('GET', '/api/sessions/runtime'),
      api<ModelsResponse>('GET', '/api/providers/claude/models'),
    ])

    if (settingsResult.status === 'fulfilled') {
      const s: SettingsData = { ...DEFAULT_SETTINGS_DATA, ...settingsResult.value }
      setData(s)
      setModel(s.llm_model)
      setDaemonInterval(s.daemon_interval)
      setDaemonMaxFiles(s.daemon_max_files)
      setModelConfigurationsText(prettyJson(s.model_configurations))
      setPromptTemplatesText(prettyJson(s.prompt_templates as Record<string, unknown>))
      setPolicyRulesText(prettyJson(s.policy_rules))
      setLoadError(null)
      setValidationError(null)
    } else {
      setData(null)
      setLoadError('設定を取得できませんでした。サーバーを再起動してください: pantheon serve')
    }

    setStorageInfo(storageResult.status === 'fulfilled' ? storageResult.value : null)
    setRuntime(runtimeResult.status === 'fulfilled' ? runtimeResult.value : null)
    if (modelsResult.status === 'fulfilled' && modelsResult.value.models.length > 0) {
      setAvailableModels(modelsResult.value.models)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError(null)

    let modelConfigurations: Record<string, unknown>
    let promptTemplates: Record<string, string>
    let policyRules: Record<string, unknown>

    try {
      if (daemonInterval < 60) {
        throw new Error('実行間隔は 60 秒以上にしてください。')
      }
      if (daemonMaxFiles < 1 || daemonMaxFiles > 1000) {
        throw new Error('最大ファイル数は 1〜1000 の範囲で指定してください。')
      }
      modelConfigurations = parseJsonObject('モデル構成', modelConfigurationsText)
      const parsedPromptTemplates = parseJsonObject('プロンプトテンプレート', promptTemplatesText)
      promptTemplates = Object.fromEntries(
        Object.entries(parsedPromptTemplates).map(([key, value]) => [key, String(value)]),
      )
      policyRules = parseJsonObject('ポリシールール', policyRulesText)
    } catch (error) {
      const message = error instanceof Error ? error.message : '設定の検証に失敗しました。'
      setValidationError(message)
      toast.error(message)
      return
    }

    setSaving(true)
    try {
      await api('PUT', '/api/settings', {
        llm_model: model,
        daemon_interval: daemonInterval,
        daemon_max_files: daemonMaxFiles,
        model_configurations: modelConfigurations,
        prompt_templates: promptTemplates,
        policy_rules: policyRules,
      })
      toast.success('設定を保存しました。')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '設定の保存に失敗しました。')
    } finally {
      setSaving(false)
    }
  }

  const effectiveData = data ?? DEFAULT_SETTINGS_DATA

  return (
    <>
      <header className="page-header">
        <div className="page-title">設定</div>
      </header>

      <div className="page-content flex flex-col gap-4">
        {loading ? (
          <div className="card">
            <div className="card-body flex items-center gap-3">
              <div className="spinner" />
              <div className="text-muted">設定を読み込み中…</div>
            </div>
          </div>
        ) : null}

        {!loading ? (
          <form onSubmit={handleSave} className="flex flex-col gap-4">
            {loadError ? (
              <div className="settings-status-bar warn">
                <span className="badge badge-yellow">要再起動</span>
                <span className="text-sm text-muted">{loadError}</span>
              </div>
            ) : null}

            {validationError ? (
              <div className="settings-status-bar warn">
                <span className="badge badge-red">検証エラー</span>
                <span className="text-sm text-muted">{validationError}</span>
              </div>
            ) : null}

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title flex items-center gap-2">
                    <Terminal size={15} />
                    実行ランタイム（Claude Code）
                  </div>
                  <div className="card-description">
                    Pantheon は API キー不要。すべてローカルの claude CLI と wmux 経由で動作します。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className={`badge ${effectiveData.has_llm || runtime?.claude.available ? 'badge-green' : 'badge-red'}`}>
                    {effectiveData.has_llm || runtime?.claude.available ? 'claude CLI 検出' : 'claude CLI 未検出'}
                  </span>
                  {runtime ? (
                    <span className={`badge ${runtime.wmux.state === 'connected' ? 'badge-green' : runtime.wmux.state === 'awaiting-approval' ? 'badge-yellow' : 'badge-neutral'}`}>
                      {wmuxLabel(runtime.wmux.state)}
                    </span>
                  ) : null}
                  {runtime ? <span className="badge badge-neutral">driver: {runtime.driver}</span> : null}
                </div>
                {runtime?.claude.binary ? (
                  <div className="storage-location">
                    <span className="text-muted text-sm">claude:</span>
                    <code className="mono text-sm">{runtime.claude.binary}</code>
                  </div>
                ) : null}

                <div className="input-group" style={{ maxWidth: '360px' }}>
                  <label className="input-label" htmlFor="llm-model">既定モデル（任意）</label>
                  <select
                    id="llm-model"
                    className="select"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  >
                    {(availableModels.length > 0 ? availableModels : [model]).map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <p className="settings-hint">省略時は claude CLI の既定モデルが使われます。</p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">高度な構成管理</div>
                  <div className="card-description">モデル構成、プロンプトテンプレート、ポリシールールを保存します。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="input-group">
                  <label className="input-label" htmlFor="model-configurations">モデル構成(JSON)</label>
                  <textarea
                    id="model-configurations"
                    className="textarea mono"
                    rows={8}
                    value={modelConfigurationsText}
                    onChange={(e) => setModelConfigurationsText(e.target.value)}
                  />
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="prompt-templates">プロンプトテンプレート(JSON)</label>
                  <textarea
                    id="prompt-templates"
                    className="textarea mono"
                    rows={8}
                    value={promptTemplatesText}
                    onChange={(e) => setPromptTemplatesText(e.target.value)}
                  />
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="policy-rules">ポリシールール(JSON)</label>
                  <textarea
                    id="policy-rules"
                    className="textarea mono"
                    rows={10}
                    value={policyRulesText}
                    onChange={(e) => setPolicyRulesText(e.target.value)}
                  />
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">デーモン設定</div>
                  <div className="card-description">バックグラウンドの自律改善ループの動作パラメータです。</div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-interval">実行間隔（秒）</label>
                    <input
                      id="daemon-interval"
                      className="input"
                      type="number"
                      min={60}
                      value={daemonInterval}
                      onChange={(e) => setDaemonInterval(Number(e.target.value))}
                    />
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-max-files">最大ファイル数</label>
                    <input
                      id="daemon-max-files"
                      className="input"
                      type="number"
                      min={1}
                      max={1000}
                      value={daemonMaxFiles}
                      onChange={(e) => setDaemonMaxFiles(Number(e.target.value))}
                    />
                  </div>
                </div>
              </div>
            </div>

            {storageInfo ? (
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">ストレージ情報</div>
                    <div className="card-description">{storageInfo.note}</div>
                  </div>
                </div>
                <div className="card-body flex flex-col gap-4">
                  <div className="storage-location">
                    <span className="text-muted text-sm">保存場所:</span>
                    <code className="mono text-sm">{storageInfo.platform_home}</code>
                  </div>
                  <div className="storage-table">
                    {Object.values(storageInfo.storage).map((entry) => (
                      <div key={entry.path} className="storage-row">
                        <div className="storage-label">{entry.label}</div>
                        <div className="storage-meta">
                          {entry.exists ? (
                            <>
                              <span className="badge badge-green text-xs">保存済み</span>
                              <span className="text-xs text-muted">{entry.file_count} ファイル</span>
                              <span className="text-xs text-muted">{formatBytes(entry.size_bytes)}</span>
                            </>
                          ) : (
                            <span className="badge badge-neutral text-xs">未作成</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            <div className="settings-save-row">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                <Save size={14} />
                {saving ? '保存中…' : '設定を保存'}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </>
  )
}
