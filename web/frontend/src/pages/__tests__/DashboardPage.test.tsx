import { screen, waitFor, within } from '@testing-library/react'
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
  platform_home: '/Users/test/pantheon',
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

type DashTask = {
  id: string
  org_name: string
  description: string
  status: string
  started_at: string
}
const emptyTaskQueue: {
  tasks: DashTask[]
  stats: { total: number; pending: number; running: number; done: number; failed: number }
} = { tasks: [], stats: { total: 0, pending: 0, running: 0, done: 0, failed: 0 } }
const emptyHistory: unknown[] = []

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

/** Default mock that handles all 6 API calls used by DashboardPage.loadData() */
function setupDefaultMock({
  organizations = [] as typeof organization[],
  daemon = { running: false, pid: null as number | null, log_path: null as string | null },
  taskQueue = emptyTaskQueue,
  history = emptyHistory,
} = {}) {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/platform/status') return platform
    if (method === 'GET' && path === '/api/settings') return settings
    if (method === 'GET' && path === '/api/organizations') return organizations
    if (method === 'GET' && path === '/api/daemon/status') return daemon
    if (method === 'GET' && path === '/api/tasks') return taskQueue
    if (method === 'GET' && path === '/api/execution-history?limit=40') return history
    throw new Error(`Unexpected request: ${method} ${path}`)
  })
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while dashboard data is loading', async () => {
    const request = deferred<typeof platform>()
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return request.promise
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return []
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    expect(screen.getByText('プラットフォーム状態を読み込み中…')).toBeInTheDocument()

    request.resolve(platform)
    await waitFor(() => {
      expect(screen.getByText('組織がありません')).toBeInTheDocument()
    })
  })

  it('renders an empty organization state with a link to create organizations', async () => {
    setupDefaultMock()
    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('組織がありません')).toBeInTheDocument()
    // LLM status badge in platform card
    expect(screen.getByText('LLM 準備完了')).toBeInTheDocument()
    // Actionable link for empty orgs state
    expect(screen.getByRole('link', { name: /組織を作成・管理する/ })).toBeInTheDocument()
  })

  it('keeps the dashboard visible when settings loading fails', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') {
        throw new Error('Unexpected token < in JSON at position 0')
      }
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
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
    setupDefaultMock({
      organizations: [organization],
      daemon: { running: true, pid: 4242, log_path: '/Users/test/daemon.log' },
    })

    renderWithRouter(<DashboardPage />)

    // Platform status
    expect(await screen.findByText('LLM 準備完了')).toBeInTheDocument()
    // Org summary
    expect(screen.getByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('Main product')).toBeInTheDocument()
    // Daemon running
    expect(screen.getByText('起動中')).toBeInTheDocument()
    // Log path shown with copy button (not just text)
    expect(screen.getByText('/Users/test/daemon.log')).toBeInTheDocument()
  })

  it('refreshes data when the update button is clicked', async () => {
    let refreshCount = 0
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      if (method === 'GET' && path === '/api/organizations') {
        refreshCount += 1
        return refreshCount === 1 ? [] : [organization]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('組織がありません')).toBeInTheDocument()
    // Single refresh button in header (label '更新')
    await user.click(screen.getByRole('button', { name: '更新' }))

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/organizations')
  })

  it('requires confirmation before initializing the platform', async () => {
    // Use uninitialized platform so the setup button is visible
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return { ...platform, initialized: false }
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return []
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      if (method === 'POST' && path === '/api/init') return { message: '初期化完了' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)
    expect(await screen.findByText('組織がありません')).toBeInTheDocument()

    // Click the "初回セットアップ" button — should open ConfirmDialog, NOT directly call API
    await user.click(screen.getByRole('button', { name: /初回セットアップ/ }))

    // Confirm dialog should appear
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/プラットフォームを初期化しますか？/)).toBeInTheDocument()

    // Cancel — API must NOT be called
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))
    expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/init')

    // Open dialog again and confirm
    await user.click(screen.getByRole('button', { name: /初回セットアップ/ }))
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: /初期化する/ }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('初期化完了')
    })
  })

  it('starts the daemon without a confirmation dialog', async () => {
    let daemonRunning = false
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') {
        return { running: daemonRunning, pid: daemonRunning ? 1001 : null, log_path: daemonRunning ? '/Users/test/daemon.log' : null }
      }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      if (method === 'POST' && path === '/api/daemon/start') {
        daemonRunning = true
        return { message: 'デーモン起動完了' }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)
    expect(await screen.findByText('alpha')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '起動' }))
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('デーモン起動完了')
    })
    expect(await screen.findByText('起動中')).toBeInTheDocument()
  })

  it('requires confirmation before stopping the daemon', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return settings
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') {
        return { running: true, pid: 9999, log_path: '/tmp/daemon.log' }
      }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      if (method === 'POST' && path === '/api/daemon/stop') return { message: 'デーモン停止完了' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DashboardPage />)
    expect(await screen.findByText('起動中')).toBeInTheDocument()

    // Click stop — should open ConfirmDialog
    await user.click(screen.getByRole('button', { name: '停止' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText(/稼働中のオーケストレーションを停止しますか？/)).toBeInTheDocument()

    // Cancel — API must NOT be called
    await user.click(within(dialog).getByRole('button', { name: 'キャンセル' }))
    expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/daemon/stop')

    // Open dialog again and confirm stop
    await user.click(screen.getByRole('button', { name: '停止' }))
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '停止する' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('デーモン停止完了')
    })
  })

  it('shows honest metric labels for 40-item window', async () => {
    setupDefaultMock()
    renderWithRouter(<DashboardPage />)

    // Should show honest label with "直近40件"
    expect(await screen.findByText('承認数（直近40件中）')).toBeInTheDocument()
    expect(screen.getByText('承認率（直近40件中）')).toBeInTheDocument()
    // Zero approved+rejected → '—' not '0%' (approval rate must not show percentage)
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument()
    // '—' appears in the approval rate metric value
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders task stats and active tasks with localized labels', async () => {
    const taskQueue = {
      tasks: [
        {
          id: 't1',
          org_name: 'alpha',
          description: 'コード分析',
          status: 'running',
          started_at: new Date(Date.now() - 30000).toISOString(),
        },
      ],
      stats: { total: 1, pending: 0, running: 1, done: 5, failed: 0 },
    }
    setupDefaultMock({ organizations: [organization], taskQueue })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('コード分析')).toBeInTheDocument()
    // Status should be localized via statusLabel（複数箇所に出るため getAllByText）
    expect(screen.getAllByText('実行中').length).toBeGreaterThan(0)
    // Daemon status '停止' label appears, task running count '1' appears
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
  })

  it('shows inbox link for proposal_created history items', async () => {
    const history = [
      {
        id: 'h1',
        timestamp: '2025-01-01T10:00:00.000Z',
        operation: 'proposal_created',
        status: 'pending',
        title: 'テスト提案',
        details: '詳細情報',
        org_name: 'alpha',
      },
    ]
    setupDefaultMock({ history })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('テスト提案')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /承認インボックスで開く/ })).toBeInTheDocument()
  })

  it('shows link to all orgs page from summary', async () => {
    setupDefaultMock({ organizations: [organization] })

    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('alpha')).toBeInTheDocument()
    // "全件を見る" link
    expect(screen.getByRole('link', { name: /全件を見る/ })).toBeInTheDocument()
  })

  it('shows empty velocity chart state when no data', async () => {
    setupDefaultMock()
    renderWithRouter(<DashboardPage />)

    expect(await screen.findByText('直近6日間のデータがありません')).toBeInTheDocument()
  })

  it('displays correct system info with updated auth hint', async () => {
    setupDefaultMock({ organizations: [organization] })
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status') return platform
      if (method === 'GET' && path === '/api/settings') return { ...settings, has_llm: false }
      if (method === 'GET' && path === '/api/organizations') return [organization]
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return emptyTaskQueue
      if (method === 'GET' && path === '/api/execution-history?limit=40') return emptyHistory
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DashboardPage />)

    // Should NOT mention "APIキーを保存" (old/wrong hint)
    await waitFor(() => {
      const hint = screen.queryByText(/APIキーを保存/)
      expect(hint).not.toBeInTheDocument()
    })
    // Should mention claude CLI authentication
    expect(await screen.findByText(/CLI でログインするか/)).toBeInTheDocument()
  })
})
