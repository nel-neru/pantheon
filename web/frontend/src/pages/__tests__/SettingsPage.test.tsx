import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { SettingsPage } from '../SettingsPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// APIトークン操作のモック
vi.mock('@/lib/token', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/token')>()
  return {
    ...actual,
    getApiToken: vi.fn(() => ''),
    setApiToken: vi.fn(),
  }
})

import { getApiToken, setApiToken } from '@/lib/token'

const mockedGetApiToken = getApiToken as ReturnType<typeof vi.fn>
const mockedSetApiToken = setApiToken as ReturnType<typeof vi.fn>

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const settings = {
  llm_model: 'claude-opus-4-8',
  daemon_interval: 3600,
  daemon_max_files: 10,
  model_configurations: { default: { temperature: 0.2, max_tokens: 4096, fallback_model: '' } },
  prompt_templates: { analysis: 'do it' },
  policy_rules: { auto_approve: { conditions: {} }, human_required: { conditions: {} }, auto_reject: { conditions: {} } },
  token_quota: { window_hours: 5, soft_limit_tokens: 80000, hard_limit_tokens: 160000 },
  notification_settings: { min_level: 'info', quiet_hours_start: 0, quiet_hours_end: 0 },
  settings_file: '/Users/test/settings.json',
  has_llm: true,
}

const runtime = {
  claude: { available: true, binary: 'C:/claude.exe' },
  wmux: { running: true, state: 'connected' },
  driver: 'wmux',
}

const models = { provider: 'claude_code', models: ['claude-opus-4-8', 'claude-sonnet-4-6'], source: 'claude-code' }

const storageInfo = {
  platform_home: '/Users/test/.pantheon',
  note: 'サーバーを再起動しても以下のデータはすべて保持されます',
  storage: {
    settings: {
      label: 'GUI設定',
      path: '/Users/test/.pantheon/gui_settings.json',
      exists: true,
      file_count: 1,
      size_bytes: 1536,
      last_modified: '2026-01-01T00:00:00+00:00',
    },
  },
}

function mockEndpoints(overrides: Partial<Record<string, unknown>> = {}) {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/settings') return overrides.settings ?? settings
    if (method === 'GET' && path === '/api/storage/info') return storageInfo
    if (method === 'GET' && path === '/api/sessions/runtime') return runtime
    if (method === 'GET' && path.startsWith('/api/providers/')) return models
    if (method === 'PUT' && path === '/api/settings') return overrides.put ?? { status: 'saved' }
    throw new Error(`Unexpected request: ${method} ${path}`)
  })
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
    mockedGetApiToken.mockReturnValue('')
  })

  it('shows a loading state while settings are loading', async () => {
    const request = deferred<typeof settings>()
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') return request.promise
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    expect(screen.getByText('設定を読み込み中…')).toBeInTheDocument()

    request.resolve(settings)
    await waitFor(() => {
      expect(screen.getByText('claude CLI 検出')).toBeInTheDocument()
    })
  })

  it('shows a load error banner when loading settings fails', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') throw new Error('settings load failed')
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText(/設定を取得できませんでした/)).toBeInTheDocument()
    expect(mockedToast.error).not.toHaveBeenCalled()
  })

  it('disables save button when settings failed to load', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') throw new Error('settings load failed')
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    await waitFor(() => {
      expect(screen.getByText(/設定を取得できませんでした/)).toBeInTheDocument()
    })
    const saveButton = screen.getByRole('button', { name: '設定を保存' })
    expect(saveButton).toBeDisabled()
  })

  it('renders runtime status and loaded settings', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)

    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()
    expect(screen.getByText('wmux 接続中')).toBeInTheDocument()
    // driver は詳細折りたたみの中に隠れている（常時表示をやめた）
    expect(screen.queryByText('driver: wmux')).not.toBeInTheDocument()
    expect(screen.getByLabelText('既定モデル（任意）')).toHaveValue('claude-opus-4-8')
    expect(screen.getByText('ストレージ情報')).toBeInTheDocument()
    expect(screen.getByText('/Users/test/.pantheon')).toBeInTheDocument()
  })

  it('shows driver badge in details section when expanded', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    await waitFor(() => expect(screen.getByText('claude CLI 検出')).toBeInTheDocument())

    // 折りたたみ展開前はドライバが見えない
    expect(screen.queryByText('wmux')).not.toBeInTheDocument()

    // 詳細ボタンを押すとドライバが見える
    await user.click(screen.getByRole('button', { name: '詳細情報' }))
    expect(screen.getByText('wmux')).toBeInTheDocument()
    expect(screen.getByText('実行ドライバ:')).toBeInTheDocument()
  })

  it('shows a saving state while the form is submitting', async () => {
    const saveRequest = deferred<{ status: string }>()
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      if (method === 'PUT' && path === '/api/settings') return saveRequest.promise
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '設定を保存' }))
    expect(screen.getByRole('button', { name: '保存中…' })).toBeDisabled()

    saveRequest.resolve({ status: 'saved' })
    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('PUT', '/api/settings', expect.objectContaining({
        llm_model: 'claude-opus-4-8',
        daemon_interval: 3600,
        daemon_max_files: 10,
        model_configurations: expect.any(Object),
        prompt_templates: expect.any(Object),
        policy_rules: expect.any(Object),
        // SET-EXPOSE: クォータ・通知設定も PUT ペイロードに含まれる
        token_quota: expect.objectContaining({ soft_limit_tokens: 80000 }),
        notification_settings: expect.objectContaining({ min_level: 'info' }),
      }))
    })
  })

  it('saves updated daemon interval without any API keys', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('実行間隔（秒）'))
    await user.type(screen.getByLabelText('実行間隔（秒）'), '7200')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })
    const putCall = mockApi.mock.calls.find((c) => c[0] === 'PUT' && c[1] === '/api/settings')
    expect(putCall?.[2]).not.toHaveProperty('anthropic_api_key')
    expect(putCall?.[2]).not.toHaveProperty('llm_provider')
    expect((putCall?.[2] as { daemon_interval: number }).daemon_interval).toBe(7200)
  })

  it('blocks save and shows inline error when daemon_interval < 60', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('実行間隔（秒）'))
    await user.type(screen.getByLabelText('実行間隔（秒）'), '30')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalled()
    })
    expect(screen.getByText('実行間隔は 60 秒以上にしてください。')).toBeInTheDocument()
    // PUT は呼ばれない
    expect(mockApi).not.toHaveBeenCalledWith('PUT', '/api/settings', expect.anything())
  })

  it('blocks save when soft limit > hard limit', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // soft=200000 hard=100000 → soft > hard
    await user.clear(screen.getByLabelText('ソフト上限（トークン）'))
    await user.type(screen.getByLabelText('ソフト上限（トークン）'), '200000')
    await user.clear(screen.getByLabelText('ハード上限（トークン）'))
    await user.type(screen.getByLabelText('ハード上限（トークン）'), '100000')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalled()
    })
    expect(screen.getByText('ソフト上限はハード上限以下にしてください。')).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalledWith('PUT', '/api/settings', expect.anything())
  })

  it('blocks save when quiet_hours are out of range', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('静音 開始（時）'))
    await user.type(screen.getByLabelText('静音 開始（時）'), '25')
    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalled()
    })
    expect(screen.getByText('静音開始時刻は 0〜23 の範囲で指定してください。')).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalledWith('PUT', '/api/settings', expect.anything())
  })

  it('does not include API token in PUT payload (C010)', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })
    const putCall = mockApi.mock.calls.find((c) => c[0] === 'PUT' && c[1] === '/api/settings')
    expect(putCall?.[2]).not.toHaveProperty('api_token')
    expect(putCall?.[2]).not.toHaveProperty('pantheon_api_token')
    expect(putCall?.[2]).not.toHaveProperty('token')
  })

  it('saves API token to localStorage via setApiToken (not /api/settings)', async () => {
    mockEndpoints()
    mockedGetApiToken.mockReturnValue('')
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    const tokenInput = screen.getByLabelText('APIトークン')
    await user.type(tokenInput, 'my-test-token')
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(mockedSetApiToken).toHaveBeenCalledWith('my-test-token')
    // PUT /api/settings には token が含まれない
    expect(mockApi).not.toHaveBeenCalledWith('PUT', '/api/settings', expect.anything())
  })

  it('shows structured policy editor by default (not raw JSON textarea)', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // 構造化エディタのセクションラベルが見える
    expect(screen.getByText('自動承認（auto_approve）')).toBeInTheDocument()
    expect(screen.getByText('人手必須（human_required）')).toBeInTheDocument()
    expect(screen.getByText('自動却下（auto_reject）')).toBeInTheDocument()

    // デフォルトでは RAW textarea は見えない
    expect(screen.queryByLabelText('ポリシールール JSON')).not.toBeInTheDocument()
  })

  it('toggles policy rules to RAW JSON mode', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // RAWトグルボタンが3つある（モデル構成・プロンプト・ポリシー）
    const rawButtons = screen.getAllByRole('button', { name: 'RAW (JSON)' })
    // ポリシーは3番目
    await user.click(rawButtons[2])

    expect(screen.getByLabelText('ポリシールール JSON')).toBeInTheDocument()
    // 構造化エディタは消える
    expect(screen.queryByText('自動承認（auto_approve）')).not.toBeInTheDocument()
  })

  it('shows structured prompt editor by default', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // プロンプトテンプレートのキー入力欄が見える
    expect(screen.getByLabelText('テンプレート 1 キー')).toBeInTheDocument()
    expect(screen.getByLabelText('テンプレート 1 本文')).toBeInTheDocument()

    // デフォルトでは RAW textarea は見えない
    expect(screen.queryByLabelText('プロンプトテンプレート JSON')).not.toBeInTheDocument()
  })

  it('shows warning when auto_approve conditions are empty', async () => {
    // policy_rules の auto_approve.conditions が空 → 警告を出す
    mockEndpoints({
      settings: {
        ...settings,
        policy_rules: {
          auto_approve: { conditions: {} },
          human_required: { conditions: {} },
          auto_reject: { conditions: {} },
        },
      },
    })
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    expect(screen.getByText(/auto_approve.*の条件が空/)).toBeInTheDocument()
  })

  it('builds correct PUT payload shape (policy_rules key structure preserved)', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })
    const putCall = mockApi.mock.calls.find((c) => c[0] === 'PUT' && c[1] === '/api/settings')
    const payload = putCall?.[2] as Record<string, unknown>

    // バックエンド互換の形状チェック
    expect(payload).toHaveProperty('llm_model')
    expect(payload).toHaveProperty('daemon_interval')
    expect(payload).toHaveProperty('daemon_max_files')
    expect(payload).toHaveProperty('model_configurations')
    expect(payload).toHaveProperty('prompt_templates')
    expect(payload).toHaveProperty('policy_rules')
    expect(payload).toHaveProperty('token_quota')
    expect(payload).toHaveProperty('notification_settings')

    // policy_rules は 3 固定キーを持つこと
    const pr = payload.policy_rules as Record<string, unknown>
    expect(pr).toHaveProperty('auto_approve')
    expect(pr).toHaveProperty('human_required')
    expect(pr).toHaveProperty('auto_reject')

    // token_quota の中身
    const tq = payload.token_quota as Record<string, number>
    expect(tq).toHaveProperty('window_hours')
    expect(tq).toHaveProperty('soft_limit_tokens')
    expect(tq).toHaveProperty('hard_limit_tokens')
  })

  it('shows dirty indicator when form is modified', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // 初期状態は dirty なし
    expect(screen.queryByText('未保存の変更があります')).not.toBeInTheDocument()

    // 何か変更する
    await user.clear(screen.getByLabelText('実行間隔（秒）'))
    await user.type(screen.getByLabelText('実行間隔（秒）'), '7200')

    expect(screen.getByText('未保存の変更があります')).toBeInTheDocument()
  })

  it('clears dirty indicator after successful save', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('実行間隔（秒）'))
    await user.type(screen.getByLabelText('実行間隔（秒）'), '7200')
    expect(screen.getByText('未保存の変更があります')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '設定を保存' }))
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })

    await waitFor(() => {
      expect(screen.queryByText('未保存の変更があります')).not.toBeInTheDocument()
    })
  })

  it('shows model list fetch error hint when models API fails', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) throw new Error('models fetch failed')
      if (method === 'PUT' && path === '/api/settings') return { status: 'saved' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    await waitFor(() => {
      expect(screen.getByText(/モデル一覧を取得できません/)).toBeInTheDocument()
    })
  })

  it('merges current model into options when not in available list', async () => {
    mockEndpoints({
      settings: { ...settings, llm_model: 'claude-opus-custom' },
    })
    renderWithRouter(<SettingsPage />)
    await waitFor(() => expect(screen.getByText('claude CLI 検出')).toBeInTheDocument())

    const select = screen.getByLabelText('既定モデル（任意）') as HTMLSelectElement
    expect(select.value).toBe('claude-opus-custom')
    // 選択肢にも含まれる
    const options = Array.from(select.options).map((o) => o.value)
    expect(options).toContain('claude-opus-custom')
  })

  it('uses runtime.claude.available for detection (not has_llm)', async () => {
    // has_llm=true だが runtime では available=false
    mockEndpoints({
      settings: { ...settings, has_llm: true },
    })
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') return { ...settings, has_llm: true }
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return {
        claude: { available: false, binary: null },
        wmux: { running: false, state: 'not-running' },
        driver: 'direct',
      }
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      if (method === 'PUT' && path === '/api/settings') return { status: 'saved' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    await waitFor(() => {
      expect(screen.getByText('claude CLI 未検出')).toBeInTheDocument()
    })
  })

  it('prompt_templates values are preserved as strings (not destroyed by String())', async () => {
    mockEndpoints({
      settings: {
        ...settings,
        prompt_templates: { myTemplate: 'Hello World' },
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // 構造化エディタでプロンプト本文が読み込まれている
    const valueInput = screen.getByLabelText('テンプレート 1 本文') as HTMLTextAreaElement
    expect(valueInput.value).toBe('Hello World')

    await user.click(screen.getByRole('button', { name: '設定を保存' }))
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('設定を保存しました。')
    })

    const putCall = mockApi.mock.calls.find((c) => c[0] === 'PUT' && c[1] === '/api/settings')
    const pt = (putCall?.[2] as Record<string, unknown>)?.prompt_templates as Record<string, string>
    expect(pt.myTemplate).toBe('Hello World')
  })

  it('blocks save and shows inline error for empty prompt template key', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // プロンプトテンプレートキーを空にする
    const keyInput = screen.getByLabelText('テンプレート 1 キー') as HTMLInputElement
    await user.clear(keyInput)

    await user.click(screen.getByRole('button', { name: '設定を保存' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalled()
    })
    expect(screen.getByText('テンプレート名（キー）を入力してください。')).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalledWith('PUT', '/api/settings', expect.anything())
  })

  it('shows storage info when available', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)
    await waitFor(() => expect(screen.getByText('ストレージ情報')).toBeInTheDocument())
    expect(screen.getByText('/Users/test/.pantheon')).toBeInTheDocument()
    expect(screen.getByText('GUI設定')).toBeInTheDocument()
    expect(screen.getByText('保存済み')).toBeInTheDocument()
  })

  it('does not show storage card when storage API fails', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/storage/info') throw new Error('storage failed')
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      if (method === 'PUT' && path === '/api/settings') return { status: 'saved' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    await waitFor(() => expect(screen.getByText('claude CLI 検出')).toBeInTheDocument())
    expect(screen.queryByText('ストレージ情報')).not.toBeInTheDocument()
  })

  it('within block: verifies structured model config editor renders temperature and max_tokens', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // 構造化モデル構成エディタが表示されている
    expect(screen.getByLabelText('temperature')).toBeInTheDocument()
    expect(screen.getByLabelText('max_tokens')).toBeInTheDocument()
    expect(screen.getByLabelText('fallback_model（任意）')).toBeInTheDocument()

    // デフォルトでは RAW textarea は見えない
    expect(screen.queryByLabelText('モデル構成 JSON')).not.toBeInTheDocument()
  })

  it('toggles model configurations to RAW JSON mode', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    const rawButtons = screen.getAllByRole('button', { name: 'RAW (JSON)' })
    await user.click(rawButtons[0]) // モデル構成

    expect(screen.getByLabelText('モデル構成 JSON')).toBeInTheDocument()
    expect(screen.queryByLabelText('temperature')).not.toBeInTheDocument()
  })

  it('blocks RAW JSON mode switch when JSON is invalid', async () => {
    mockEndpoints()
    const user = userEvent.setup()
    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()

    // まずRAWモードに切り替える
    const rawButtons = screen.getAllByRole('button', { name: 'RAW (JSON)' })
    await user.click(rawButtons[0])

    // RAWテキストに不正なJSONを入力（userEvent では { } は特殊文字なので fireEvent で直接設定）
    const rawTextarea = screen.getByLabelText('モデル構成 JSON')
    await user.clear(rawTextarea)
    await user.type(rawTextarea, 'invalid json text')

    // 構造化に戻そうとする → エラーが出てトグルできない
    const backButton = screen.getByRole('button', { name: '構造化エディタ' })
    await user.click(backButton)

    // エラーメッセージが出る
    expect(screen.getByText(/JSON 構文が不正/)).toBeInTheDocument()
    // RAW テキストエリアはまだ表示されている（トグルできていない）
    expect(screen.getByLabelText('モデル構成 JSON')).toBeInTheDocument()
  })
})
