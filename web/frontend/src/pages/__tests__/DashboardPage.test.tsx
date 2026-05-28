import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { DashboardPage } from '../DashboardPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const platform = {
  group_health_score: 82,
  balance_score: 64,
  total_organizations: 1,
  active_organizations: 1,
  weakest_organization: null,
  strongest_organization: 'alpha',
  platform_home: '/Users/test/repocorp_ai',
  initialized: true,
  has_llm: true,
}

const settings = {
  llm_provider: 'anthropic',
  llm_model: 'claude-3-5-sonnet-20241022',
  settings_file: '/Users/test/settings.json',
  has_llm: true,
}

const organization = {
  id: 'org-1',
  name: 'alpha',
  purpose: 'Main product',
  health_score: 76,
  autonomy_score: 60,
  total_agents: 4,
  pending_proposals: 2,
  target_repo_path: '/Users/test/repos/alpha',
  status: 'active',
  last_active: '2025-01-01T10:00:00.000Z',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while dashboard data is loading', async () => {
    const request = deferred<typeof platform>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return request.promise
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return []
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    expect(screen.getByText('プラットフォーム状態を読み込み中…')).toBeInTheDocument()

    request.resolve(platform)
    await waitFor(() => {
      expect(screen.getByText('組織がありません')).toBeInTheDocument()
    })
  })

  it('renders an empty organization state', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return []
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('組織がありません')).toBeInTheDocument()
    expect(screen.getByText('LLM 接続済み')).toBeInTheDocument()
  })

  it('keeps the dashboard visible when settings loading fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') {
        throw new Error('Unexpected token < in JSON at position 0')
      }
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') {
        return { running: false, pid: null, log_path: null }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(screen.getAllByText('要再起動')).not.toHaveLength(0)
    expect(
      screen.getByText(/システム情報を取得できませんでした。サーバーを再起動してください:/),
    ).toBeInTheDocument()
    expect(mockedToast.error).not.toHaveBeenCalled()
  })

  it('renders loaded platform, organization, and daemon data', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') {
        return { running: true, pid: 4242, log_path: '/Users/test/daemon.log' }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('LLM 準備完了')).toBeInTheDocument()
    expect(screen.getByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('Main product')).toBeInTheDocument()
    expect(screen.getByText('起動中')).toBeInTheDocument()
    expect(screen.getByText('/Users/test/daemon.log')).toBeInTheDocument()
  })

  it('refreshes data when the update button is clicked', async () => {
    let refreshCount = 0
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/organizations') {
        refreshCount += 1
        return refreshCount === 1 ? [] : [organization]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('組織がありません')).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '更新' })[0])

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/organizations')
  })

  it('initializes the platform and starts the daemon', async () => {
    let daemonRunning = false
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') {
        return { running: daemonRunning, pid: daemonRunning ? 1001 : null, log_path: daemonRunning ? '/Users/test/daemon.log' : null }
      }
      if (method === 'POST' && path === '/api/init') {
        return { message: '初期化完了' }
      }
      if (method === 'POST' && path === '/api/daemon/start') {
        daemonRunning = true
        return { message: 'デーモン起動完了' }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('alpha')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '初期化' }))
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('初期化完了')
    })

    await user.click(screen.getByRole('button', { name: '起動' }))
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('デーモン起動完了')
    })
    expect(await screen.findByText('起動中')).toBeInTheDocument()
  })
})
