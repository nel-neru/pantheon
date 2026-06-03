import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { SettingsPage } from '../SettingsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const settings = {
  llm_provider: 'anthropic',
  llm_model: 'claude-3-5-sonnet-20241022',
  anthropic_api_key_masked: 'sk-ant-****',
  openai_api_key_masked: 'sk-****',
  groq_api_key_masked: 'gsk_****',
  github_models_api_key_masked: 'ghp_****',
  gemini_api_key_masked: 'AIza****',
  anthropic_api_key_set: true,
  openai_api_key_set: false,
  groq_api_key_set: false,
  github_models_api_key_set: false,
  gemini_api_key_set: false,
  daemon_interval: 3600,
  daemon_max_files: 10,
  settings_file: '/Users/test/settings.json',
  has_llm: true,
}

const storageInfo = {
  platform_home: '/Users/test/.repocorp',
  note: 'サーバーを再起動しても以下のデータはすべて保持されます',
  storage: {
    settings: {
      label: 'GUI設定（LLMプロバイダー・APIキー等）',
      path: '/Users/test/.repocorp/gui_settings.json',
      exists: true,
      file_count: 1,
      size_bytes: 1536,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
    organizations: {
      label: '組織定義',
      path: '/Users/test/.repocorp/organizations',
      exists: true,
      file_count: 2,
      size_bytes: 4096,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
    chat_sessions: {
      label: 'チャットセッション履歴',
      path: '/Users/test/.repocorp/chat_sessions',
      exists: true,
      file_count: 4,
      size_bytes: 5120,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
    task_queue: {
      label: 'タスクキュー',
      path: '/Users/test/.repocorp/task_queue.json',
      exists: true,
      file_count: 1,
      size_bytes: 512,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
    goal_history: {
      label: 'ゴール実行履歴',
      path: '/Users/test/.repocorp/goal_history.json',
      exists: true,
      file_count: 1,
      size_bytes: 256,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
    knowledge: {
      label: 'ナレッジファイル',
      path: '/Users/test/knowledge',
      exists: true,
      file_count: 3,
      size_bytes: 3072,
      last_modified: '2025-01-01T00:00:00+00:00',
    },
  },
}

const providerModels = {
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'],
  openai: ['gpt-4o', 'gpt-4o-mini'],
  groq: ['llama-3.1-70b-versatile', 'mixtral-8x7b-32768'],
  github_models: ['gpt-4o', 'claude-3-5-sonnet'],
  gemini: ['gemini-2.0-flash', 'gemini-1.5-pro'],
} as const

type ModelSource = 'api' | 'fallback' | 'cache'

function isModelsRequest(method: string, path: string) {
  return method === 'GET' && path.startsWith('/api/providers/') && path.endsWith('/models')
}

function isStorageInfoRequest(method: string, path: string) {
  return method === 'GET' && path === '/api/storage/info'
}

function buildModelsResponse(
  path: string,
  sourceByProvider: Partial<Record<string, ModelSource>> = {},
) {
  const provider = path.split('/')[3] ?? ''
  return {
    provider,
    models: [...(providerModels[provider as keyof typeof providerModels] ?? [])],
    source: sourceByProvider[provider] ?? 'fallback',
    capabilities: {
      provider,
      supports_tools: true,
      supports_json_mode: false,
      supports_streaming: true,
      supports_streaming_tools: false,
      supports_reasoning_effort: false,
      supports_system_prompt: true,
      max_context_tokens: 200000,
      notes: 'test caps',
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while settings are loading', async () => {
    const request = deferred<typeof settings>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return request.promise
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path)
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)

    expect(screen.getByText('設定を読み込み中…')).toBeInTheDocument()

    request.resolve(settings)
    await waitFor(() => {
      expect(screen.getByText('LLM 接続済み')).toBeInTheDocument()
    })
  })

  it('shows a restart banner and fallback form when loading settings fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        throw new Error('settings load failed')
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path)
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)

    expect(await screen.findByText('要再起動')).toBeInTheDocument()
    expect(
      screen.getByText(/設定を取得できませんでした。サーバーを再起動してください:/),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('プロバイダー')).toHaveValue('anthropic')
    expect(screen.getByLabelText('モデル')).toHaveValue('claude-3-5-sonnet-20241022')
    expect(screen.getByRole('button', { name: '設定を保存' })).toBeInTheDocument()
    expect(mockedToast.error).not.toHaveBeenCalled()
  })

  it('renders loaded settings data', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return settings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path)
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)

    expect(await screen.findByLabelText('プロバイダー')).toHaveValue('anthropic')
    expect(screen.getByLabelText('モデル')).toHaveValue('claude-3-5-sonnet-20241022')
    expect(screen.getAllByText('設定済み')).toHaveLength(1)
    expect(screen.getByText('ストレージ情報')).toBeInTheDocument()
    expect(screen.getByText('/Users/test/.repocorp')).toBeInTheDocument()
    expect(screen.getByText('GUI設定（LLMプロバイダー・APIキー等）')).toBeInTheDocument()
    expect(screen.getByText('1.5 KB')).toBeInTheDocument()
    expect(screen.getByText('APIキーを設定すると最新モデル一覧が取得されます')).toBeInTheDocument()
  })

  it('loads the model list dynamically', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return settings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path, { anthropic: 'api' })
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)

    expect(await screen.findByText('最新')).toBeInTheDocument()
    expect(screen.getByText('APIから最新のモデル一覧を取得しました')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/providers/anthropic/models')
    expect(screen.getByRole('option', { name: 'claude-3-opus-20240229' })).toBeInTheDocument()

    // プロバイダー能力チップが表示される（Phase 1 capabilities の UI 反映）
    expect(screen.getByText('このプロバイダーの対応機能')).toBeInTheDocument()
    expect(screen.getByText('ツール呼び出し')).toBeInTheDocument()
    expect(screen.getByText('文脈 200K tok')).toBeInTheDocument()
  })

  it('refetches models when the provider changes and resets the model selection', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return settings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path, { openai: 'api' })
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)

    expect(await screen.findByLabelText('プロバイダー')).toHaveValue('anthropic')

    await user.selectOptions(screen.getByLabelText('プロバイダー'), 'openai')

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('GET', '/api/providers/openai/models')
    })
    await waitFor(() => {
      expect(screen.getByLabelText('プロバイダー')).toHaveValue('openai')
      expect(screen.getByLabelText('モデル')).toHaveValue('gpt-4o')
    })
    expect(screen.getByRole('option', { name: 'gpt-4o-mini' })).toBeInTheDocument()
  })

  it('shows a manual model input when loading models fails and allows retry', async () => {
    let modelCalls = 0
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return settings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        modelCalls += 1
        if (modelCalls === 1) {
          throw new Error('models load failed')
        }
        return buildModelsResponse(path, { anthropic: 'api' })
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)

    expect((await screen.findAllByText('取得失敗')).length).toBeGreaterThan(0)
    expect(screen.getByText('models load failed')).toBeInTheDocument()
    expect(screen.getByText('モデル一覧の取得に失敗しました。手動でモデル名を入力してください')).toBeInTheDocument()
    expect(screen.getByLabelText('モデル')).toBeDisabled()
    expect(screen.getByLabelText('モデル名を直接入力')).toHaveValue('claude-3-5-sonnet-20241022')

    await user.click(screen.getByRole('button', { name: '再試行' }))

    expect(await screen.findByText('最新')).toBeInTheDocument()
    expect(screen.queryByText('models load failed')).not.toBeInTheDocument()
  })

  it('shows a saving state while the form is being submitted', async () => {
    const saveRequest = deferred<{ ok: boolean }>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/settings') {
        return settings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path)
      }
      if (method === 'PUT' && path === '/api/settings') {
        return saveRequest.promise
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)

    expect(await screen.findByLabelText('プロバイダー')).toHaveValue('anthropic')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    expect(screen.getByRole('button', { name: '保存中…' })).toBeDisabled()

    saveRequest.resolve({ ok: true })
    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('PUT', '/api/settings', expect.objectContaining({
        llm_provider: 'anthropic',
        llm_model: 'claude-3-5-sonnet-20241022',
        daemon_interval: 3600,
        daemon_max_files: 10,
        model_configurations: expect.any(Object),
        prompt_templates: expect.any(Object),
        policy_rules: expect.any(Object),
      }))
    })
  })

  it('saves updated settings and clears entered API keys', async () => {
    let currentSettings = settings
    mockApi.mockImplementation(async (method, path, body) => {
      if (method === 'GET' && path === '/api/settings') {
        return currentSettings
      }
      if (isStorageInfoRequest(method, path)) {
        return storageInfo
      }
      if (isModelsRequest(method, path)) {
        return buildModelsResponse(path, { openai: 'api' })
      }
      if (method === 'PUT' && path === '/api/settings') {
        currentSettings = {
          ...currentSettings,
          llm_provider: (body as { llm_provider: string }).llm_provider,
          llm_model: (body as { llm_model: string }).llm_model,
          daemon_interval: (body as { daemon_interval: number }).daemon_interval,
          daemon_max_files: (body as { daemon_max_files: number }).daemon_max_files,
          openai_api_key_set: true,
        }
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)

    expect(await screen.findByLabelText('プロバイダー')).toHaveValue('anthropic')

    await user.selectOptions(screen.getByLabelText('プロバイダー'), 'openai')
    await waitFor(() => {
      expect(screen.getByLabelText('モデル')).toHaveValue('gpt-4o')
    })
    await user.clear(screen.getByLabelText('OpenAI API キー'))
    await user.type(screen.getByLabelText('OpenAI API キー'), 'sk-new-openai')
    await user.clear(screen.getByLabelText('実行間隔（秒）'))
    await user.type(screen.getByLabelText('実行間隔（秒）'), '7200')
    await user.clear(screen.getByLabelText('最大ファイル数'))
    await user.type(screen.getByLabelText('最大ファイル数'), '25')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })
    expect(mockApi).toHaveBeenCalledWith('PUT', '/api/settings', expect.objectContaining({
      llm_provider: 'openai',
      llm_model: 'gpt-4o',
      daemon_interval: 7200,
      daemon_max_files: 25,
      openai_api_key: 'sk-new-openai',
      model_configurations: expect.any(Object),
      prompt_templates: expect.any(Object),
      policy_rules: expect.any(Object),
    }))
    expect(screen.getByLabelText('OpenAI API キー')).toHaveValue('')
  })
})
