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
  llm_model: 'claude-opus-4-8',
  daemon_interval: 3600,
  daemon_max_files: 10,
  model_configurations: { default: { temperature: 0.2 } },
  prompt_templates: { analysis: 'do it' },
  policy_rules: { auto_approve: {}, human_required: {}, auto_reject: {} },
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
    mockStreamSSE.mockReset()
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

  it('shows a restart banner when loading settings fails', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/settings') throw new Error('settings load failed')
      if (method === 'GET' && path === '/api/storage/info') return storageInfo
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.startsWith('/api/providers/')) return models
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SettingsPage />)
    expect(await screen.findByText('要再起動')).toBeInTheDocument()
    expect(screen.getByText(/設定を取得できませんでした/)).toBeInTheDocument()
    expect(mockedToast.error).not.toHaveBeenCalled()
  })

  it('renders runtime status and loaded settings', async () => {
    mockEndpoints()
    renderWithRouter(<SettingsPage />)

    expect(await screen.findByText('claude CLI 検出')).toBeInTheDocument()
    expect(screen.getByText('wmux 接続中')).toBeInTheDocument()
    expect(screen.getByText('driver: wmux')).toBeInTheDocument()
    expect(screen.getByLabelText('既定モデル（任意）')).toHaveValue('claude-opus-4-8')
    expect(screen.getByText('ストレージ情報')).toBeInTheDocument()
    expect(screen.getByText('/Users/test/.pantheon')).toBeInTheDocument()
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
      }))
    })
  })

  it('saves updated settings without any API keys', async () => {
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
})
