import { useCallback, useEffect, useState } from 'react'
import { Check, Eye, EyeOff, Save } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { formatBytes } from '@/lib/utils'

type SettingsData = {
  llm_provider: string
  llm_model: string
  anthropic_api_key_masked: string
  openai_api_key_masked: string
  groq_api_key_masked: string
  github_models_api_key_masked: string
  gemini_api_key_masked: string
  anthropic_api_key_set: boolean
  openai_api_key_set: boolean
  groq_api_key_set: boolean
  github_models_api_key_set: boolean
  gemini_api_key_set: boolean
  daemon_interval: number
  daemon_max_files: number
  settings_file: string
  has_llm: boolean
}

type ModelsResponse = {
  provider: string
  models: string[]
  source: string
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

type ModelsSource = 'api' | 'fallback' | 'cache' | null

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  groq: 'Groq',
  github_models: 'GitHub Models (無料)',
  gemini: 'Google Gemini',
}

const DEFAULT_SETTINGS_DATA: SettingsData = {
  llm_provider: 'anthropic',
  llm_model: 'claude-3-5-sonnet-20241022',
  anthropic_api_key_masked: '',
  openai_api_key_masked: '',
  groq_api_key_masked: '',
  github_models_api_key_masked: '',
  gemini_api_key_masked: '',
  anthropic_api_key_set: false,
  openai_api_key_set: false,
  groq_api_key_set: false,
  github_models_api_key_set: false,
  gemini_api_key_set: false,
  daemon_interval: 3600,
  daemon_max_files: 10,
  settings_file: '—',
  has_llm: false,
}

function ApiKeyField({
  id,
  label,
  placeholder,
  masked,
  isSet,
  value,
  onChange,
  help,
}: {
  id: string
  label: string
  placeholder: string
  masked: string
  isSet: boolean
  value: string
  onChange: (v: string) => void
  help?: string
}) {
  const [show, setShow] = useState(false)

  return (
    <div className="input-group">
      <div className="settings-label-row">
        <label className="input-label" htmlFor={id}>
          {label}
        </label>
        {isSet && value === '' ? (
          <span className="badge badge-green">
            <Check size={10} />
            設定済み
          </span>
        ) : null}
      </div>
      <div className="settings-key-row">
        <input
          id={id}
          className="input"
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isSet && value === '' ? masked || '••••••••••••••••' : placeholder}
          autoComplete="off"
        />
        <button
          type="button"
          className="btn btn-ghost btn-icon"
          onClick={() => setShow((v) => !v)}
          aria-label={show ? '隠す' : '表示'}
          tabIndex={-1}
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
      {help ? <p className="settings-hint">{help}</p> : null}
      {isSet && value === '' ? (
        <p className="settings-hint">新しい値を入力すると上書きされます。空欄のままにすると変更されません。</p>
      ) : null}
    </div>
  )
}

export function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null)

  // Form fields
  const [provider, setProvider] = useState(DEFAULT_SETTINGS_DATA.llm_provider)
  const [model, setModel] = useState(DEFAULT_SETTINGS_DATA.llm_model)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsSource, setModelsSource] = useState<ModelsSource>(null)
  const [anthropicKey, setAnthropicKey] = useState('')
  const [openaiKey, setOpenaiKey] = useState('')
  const [groqKey, setGroqKey] = useState('')
  const [githubModelsKey, setGitHubModelsKey] = useState('')
  const [geminiKey, setGeminiKey] = useState('')
  const [daemonInterval, setDaemonInterval] = useState(3600)
  const [daemonMaxFiles, setDaemonMaxFiles] = useState(10)

  const load = useCallback(async () => {
    setLoading(true)
    const [settingsResult, storageResult] = await Promise.allSettled([
      api<SettingsData>('GET', '/api/settings'),
      api<StorageInfo>('GET', '/api/storage/info'),
    ])

    if (settingsResult.status === 'fulfilled') {
      const s = settingsResult.value
      setData(s)
      setProvider(s.llm_provider)
      setModel(s.llm_model)
      setDaemonInterval(s.daemon_interval)
      setDaemonMaxFiles(s.daemon_max_files)
      setLoadError(null)
    } else {
      setData(null)
      setLoadError('設定を取得できませんでした。サーバーを再起動してください: python main.py serve')
    }

    setStorageInfo(storageResult.status === 'fulfilled' ? storageResult.value : null)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const fetchModels = useCallback(async (selectedProvider: string) => {
    setModelsLoading(true)
    try {
      const result = await api<ModelsResponse>('GET', `/api/providers/${selectedProvider}/models`)
      const normalizedSource: ModelsSource =
        result.source === 'api' || result.source === 'fallback' || result.source === 'cache'
          ? result.source
          : null
      setAvailableModels(result.models)
      setModelsSource(normalizedSource)
      setModel((currentModel) => {
        if (result.models.length > 0 && !result.models.includes(currentModel)) {
          return result.models[0]
        }
        return currentModel
      })
    } catch {
      setAvailableModels([])
      setModelsSource(null)
    } finally {
      setModelsLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchModels(provider)
  }, [provider, fetchModels])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        llm_provider: provider,
        llm_model: model,
        daemon_interval: daemonInterval,
        daemon_max_files: daemonMaxFiles,
      }
      if (anthropicKey) body.anthropic_api_key = anthropicKey
      if (openaiKey) body.openai_api_key = openaiKey
      if (groqKey) body.groq_api_key = groqKey
      if (githubModelsKey) body.github_models_api_key = githubModelsKey
      if (geminiKey) body.gemini_api_key = geminiKey

      await api('PUT', '/api/settings', body)
      toast.success('設定を保存しました。')
      setAnthropicKey('')
      setOpenaiKey('')
      setGroqKey('')
      setGitHubModelsKey('')
      setGeminiKey('')
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

            {/* LLM Status */}
            <div className={`settings-status-bar ${effectiveData.has_llm ? 'ok' : 'warn'}`}>
              <span className={`badge ${effectiveData.has_llm ? 'badge-green' : 'badge-red'}`}>
                {effectiveData.has_llm ? 'LLM 接続済み' : 'LLM 未設定'}
              </span>
              <span className="text-sm text-muted">
                {effectiveData.has_llm
                  ? '現在のプロバイダーで LLM が利用可能です。'
                  : 'API キーを設定してください。設定後すぐに反映されます。'}
              </span>
            </div>

            {/* LLM Provider */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">LLM プロバイダー設定</div>
                  <div className="card-description">
                    AI エージェントが使用する言語モデルの接続先と API キーを設定します。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="llm-provider">
                      プロバイダー
                    </label>
                    <select
                      id="llm-provider"
                      className="select"
                      value={provider}
                      onChange={(e) => setProvider(e.target.value)}
                    >
                      {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="input-group">
                    <div className="settings-label-row">
                      <label className="input-label" htmlFor="llm-model">
                        モデル
                      </label>
                      <div className="flex items-center gap-2">
                        {modelsLoading ? <span className="text-xs text-muted">読み込み中...</span> : null}
                        {modelsSource === 'api' ? (
                          <span className="badge badge-green text-xs">最新</span>
                        ) : null}
                        {modelsSource === 'fallback' ? (
                          <span className="badge badge-yellow text-xs">デフォルト</span>
                        ) : null}
                        {modelsSource === 'cache' ? (
                          <span className="badge badge-neutral text-xs">キャッシュ</span>
                        ) : null}
                        {modelsSource === null && !modelsLoading ? (
                          <span className="badge badge-red text-xs">取得失敗</span>
                        ) : null}
                      </div>
                    </div>
                    <select
                      id="llm-model"
                      className="select"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={modelsLoading || availableModels.length === 0}
                    >
                      {modelsLoading ? <option value="">読み込み中...</option> : null}
                      {!modelsLoading && availableModels.length === 0 ? (
                        <option value={model}>{model || 'モデルを選択'}</option>
                      ) : null}
                      {!modelsLoading
                        ? availableModels.map((availableModel) => (
                            <option key={availableModel} value={availableModel}>
                              {availableModel}
                            </option>
                          ))
                        : null}
                    </select>
                    <p className="settings-hint">
                      {modelsSource === 'api'
                        ? 'APIから最新のモデル一覧を取得しました'
                        : modelsSource === 'fallback'
                          ? 'APIキーを設定すると最新モデル一覧が取得されます'
                          : modelsSource === 'cache'
                            ? 'キャッシュからモデル一覧を読み込みました'
                            : modelsSource === null && !modelsLoading
                              ? 'モデル一覧の取得に失敗しました。手動でモデル名を入力してください'
                              : ''}
                    </p>
                    {modelsSource === null && !modelsLoading ? (
                      <div className="input-group mt-2">
                        <label className="input-label" htmlFor="llm-model-manual">
                          モデル名を直接入力
                        </label>
                        <input
                          id="llm-model-manual"
                          type="text"
                          className="input"
                          value={model}
                          onChange={(e) => setModel(e.target.value)}
                          placeholder="例: claude-3-5-sonnet-20241022"
                        />
                      </div>
                    ) : null}
                  </div>
                </div>

                <ApiKeyField
                  id="anthropic-key"
                  label="Anthropic API キー"
                  placeholder="sk-ant-..."
                  masked={effectiveData.anthropic_api_key_masked}
                  isSet={effectiveData.anthropic_api_key_set}
                  value={anthropicKey}
                  onChange={setAnthropicKey}
                />

                <ApiKeyField
                  id="openai-key"
                  label="OpenAI API キー"
                  placeholder="sk-..."
                  masked={effectiveData.openai_api_key_masked}
                  isSet={effectiveData.openai_api_key_set}
                  value={openaiKey}
                  onChange={setOpenaiKey}
                />

                <ApiKeyField
                  id="groq-key"
                  label="Groq API キー"
                  placeholder="gsk_..."
                  masked={effectiveData.groq_api_key_masked}
                  isSet={effectiveData.groq_api_key_set}
                  value={groqKey}
                  onChange={setGroqKey}
                />

                <ApiKeyField
                  id="github-models-key"
                  label="GitHub Personal Access Token"
                  placeholder="ghp_..."
                  masked={effectiveData.github_models_api_key_masked}
                  isSet={effectiveData.github_models_api_key_set}
                  value={githubModelsKey}
                  onChange={setGitHubModelsKey}
                  help="github.com/settings/tokens で作成。Copilot/AI機能が有効なトークンが必要です。"
                />

                <ApiKeyField
                  id="gemini-key"
                  label="Google AI API キー"
                  placeholder="AIza..."
                  masked={effectiveData.gemini_api_key_masked}
                  isSet={effectiveData.gemini_api_key_set}
                  value={geminiKey}
                  onChange={setGeminiKey}
                  help="aistudio.google.com/app/apikey で取得できます。無料枠あり。"
                />
              </div>
            </div>

            {/* Daemon Settings */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">デーモン設定</div>
                  <div className="card-description">
                    バックグラウンドで動作する自律改善ループの動作パラメータです。
                  </div>
                </div>
              </div>
              <div className="card-body flex flex-col gap-4">
                <div className="settings-row-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-interval">
                      実行間隔（秒）
                    </label>
                    <input
                      id="daemon-interval"
                      className="input"
                      type="number"
                      min={60}
                      value={daemonInterval}
                      onChange={(e) => setDaemonInterval(Number(e.target.value))}
                    />
                    <p className="settings-hint">
                      {Math.floor(daemonInterval / 3600) > 0
                        ? `${Math.floor(daemonInterval / 3600)} 時間`
                        : ''}{' '}
                      {Math.floor((daemonInterval % 3600) / 60) > 0
                        ? `${Math.floor((daemonInterval % 3600) / 60)} 分`
                        : ''}
                      ごとに改善ループが実行されます。
                    </p>
                  </div>

                  <div className="input-group">
                    <label className="input-label" htmlFor="daemon-max-files">
                      最大ファイル数
                    </label>
                    <input
                      id="daemon-max-files"
                      className="input"
                      type="number"
                      min={1}
                      max={100}
                      value={daemonMaxFiles}
                      onChange={(e) => setDaemonMaxFiles(Number(e.target.value))}
                    />
                    <p className="settings-hint">1 サイクルで分析するファイルの上限数です。</p>
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

            {/* Save button */}
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
