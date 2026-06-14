import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { SessionsPage } from '../SessionsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const runtime = {
  claude: { available: true, binary: 'C:/claude.exe' },
  wmux: { running: true, state: 'connected' },
  driver: 'wmux',
}

const session = {
  id: 'review-1',
  name: 'Review',
  driver: 'wmux',
  status: 'completed',
  created_at: '2026-06-03T00:00:00Z',
  workspace: { id: 'session:Review', name: 'Review' },
  surfaces: [
    { id: 's1', title: 'Greeter', agent_id: 'agent:greeter', status: 'done', exit_code: 0 },
  ],
}

const runningSession = {
  id: 'run-1',
  name: 'Active Run',
  driver: 'wmux',
  status: 'running',
  created_at: '2026-06-03T01:00:00Z',
  workspace: { id: 'session:ActiveRun', name: 'ActiveRun' },
  surfaces: [
    { id: 's2', title: 'Worker', agent_id: 'agent:worker', status: 'running', exit_code: null },
  ],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('SessionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while sessions are loading', async () => {
    const request = deferred<{ sessions: typeof session[] }>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return request.promise
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(screen.getByText('セッションを読み込み中…')).toBeInTheDocument()

    request.resolve({ sessions: [] })
    await waitFor(() => {
      expect(screen.getByText('セッションがありません')).toBeInTheDocument()
    })
  })

  it('renders an empty state when there are no sessions', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('セッションがありません')).toBeInTheDocument()
    expect(screen.getByText('claude CLI 検出')).toBeInTheDocument()
    expect(screen.getByText('wmux 接続中')).toBeInTheDocument()
  })

  it('shows an error state when the sessions request fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') throw new Error('session load failed')
      return runtime
    })

    renderWithRouter(<SessionsPage />)
    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('session load failed')
    })
    expect(await screen.findByText('セッションの読み込みに失敗しました')).toBeInTheDocument()
  })

  it('renders session and agent data with Japanese status labels', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Greeter')).toBeInTheDocument()
    expect(screen.getByText('agent:greeter')).toBeInTheDocument()
    // Status should be Japanese (via statusLabel)
    expect(screen.getAllByText('完了').length).toBeGreaterThan(0)
    // English raw status should NOT appear in badges
    expect(screen.queryByText('done')).not.toBeInTheDocument()
    expect(screen.queryByText('completed')).not.toBeInTheDocument()
  })

  it('shows runtime status card always, even when runtime fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [] }
      if (method === 'GET' && path === '/api/sessions/runtime') throw new Error('runtime error')
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    // Card should still render with error indicator
    expect(await screen.findByText('ランタイム状態を取得できません')).toBeInTheDocument()
  })

  it('shows wmux badge with Japanese label', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('wmux 接続中')).toBeInTheDocument()
  })

  it('shows wmux awaiting-approval badge with "承認する" link', async () => {
    const awaitingRuntime = { ...runtime, wmux: { running: false, state: 'awaiting-approval' } }
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [] }
      if (method === 'GET' && path === '/api/sessions/runtime') return awaitingRuntime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('wmux 承認待ち')).toBeInTheDocument()
    expect(screen.getByText('承認する')).toBeInTheDocument()
  })

  it('shows claude CLI not found badge with install link', async () => {
    const unavailableRuntime = { ...runtime, claude: { available: false, binary: null } }
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [] }
      if (method === 'GET' && path === '/api/sessions/runtime') return unavailableRuntime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('claude CLI 未検出')).toBeInTheDocument()
    expect(screen.getByText('インストール手順')).toBeInTheDocument()
  })

  it('opens an agent log when 表示 is clicked', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path === '/api/sessions/review-1/agents/agent%3Agreeter/log') {
        return { log: 'Hello from the greeter agent' }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Greeter')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '表示' }))
    expect(await screen.findByText('Hello from the greeter agent')).toBeInTheDocument()
  })

  it('shows error state (not log text) when log fetch fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.includes('/log')) throw new Error('ログの取得に失敗しました。')
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Greeter')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '表示' }))
    expect(await screen.findByText('ログの取得に失敗しました')).toBeInTheDocument()
    // The error should be in a separate error heading, not in the pre element
    const heading = screen.getByRole('heading', { name: 'ログの取得に失敗しました' })
    expect(heading).toBeInTheDocument()
  })

  it('stop button opens a ConfirmDialog (not instant stop)', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [runningSession] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Active Run')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Active Run を停止' }))

    // ConfirmDialog should appear
    expect(await screen.findByText('Active Run を停止しますか？')).toBeInTheDocument()
    expect(screen.getByText('停止する')).toBeInTheDocument()
    // Stop API should NOT have been called yet
    expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/sessions/run-1/stop')
  })

  it('calls stop API and shows success after confirming in ConfirmDialog', async () => {
    mockApi
      .mockResolvedValueOnce({ sessions: [runningSession] }) // initial load sessions
      .mockResolvedValueOnce(runtime)                        // initial load runtime
      .mockResolvedValueOnce(undefined)                      // POST stop
      .mockResolvedValueOnce({ sessions: [] })               // reload sessions
      .mockResolvedValueOnce(runtime)                        // reload runtime

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Active Run')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Active Run を停止' }))

    // ConfirmDialog should be visible
    expect(await screen.findByText('Active Run を停止しますか？')).toBeInTheDocument()

    // Click the confirm button in the dialog
    const confirmBtn = screen.getByRole('button', { name: '停止する' })
    await user.click(confirmBtn)

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/sessions/run-1/stop')
    })
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('セッションを停止しました。')
    })
  })

  it('cancelling ConfirmDialog does not call stop API', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [runningSession] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Active Run')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Active Run を停止' }))

    expect(await screen.findByText('Active Run を停止しますか？')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => {
      expect(screen.queryByText('Active Run を停止しますか？')).not.toBeInTheDocument()
    })
    expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/sessions/run-1/stop')
  })

  it('stop button is disabled for completed sessions', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('Review')).toBeInTheDocument()

    const stopBtn = screen.getByRole('button', { name: 'Review を停止' })
    expect(stopBtn).toBeDisabled()
  })

  it('highlights exit_code != 0 in red', async () => {
    const failedSurface = { ...session.surfaces[0], exit_code: 1 }
    const sessionWithFailure = { ...session, surfaces: [failedSurface] }
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [sessionWithFailure] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('Greeter')).toBeInTheDocument()

    // Exit code cell should have red styling
    const exitCodeCell = screen.getByText('1')
    expect(exitCodeCell).toHaveClass('text-red-600')
  })

  it('highlights the selected log row', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.includes('/log')) return { log: 'log output' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    expect(await screen.findByText('Greeter')).toBeInTheDocument()
    // The 表示 button should start as ghost
    const viewBtn = screen.getByRole('button', { name: '表示' })
    expect(viewBtn).toHaveClass('btn-ghost')

    await user.click(viewBtn)
    await screen.findByText('log output')

    // After selection the button should be primary (active state)
    expect(viewBtn).toHaveClass('btn-primary')
  })

  it('shows created_at date in the session card', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('Review')).toBeInTheDocument()
    // created_at should be formatted (not raw ISO)
    expect(screen.queryByText('2026-06-03T00:00:00Z')).not.toBeInTheDocument()
  })

  it('clears stale log when selected session disappears after reload', async () => {
    let callCount = 0
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') {
        callCount++
        // First call: return session; second call: session is gone
        return callCount === 1 ? { sessions: [session] } : { sessions: [] }
      }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      if (method === 'GET' && path.includes('/log')) return { log: 'some log' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<SessionsPage />)

    // Open log for a session
    expect(await screen.findByText('Greeter')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '表示' }))
    expect(await screen.findByText('some log')).toBeInTheDocument()

    // Manually trigger a reload (simulate retry)
    const refreshBtn = screen.getByRole('button', { name: '再読み込み' })
    await user.click(refreshBtn)

    // Log panel should clear since session is gone
    await waitFor(() => {
      expect(screen.queryByText('some log')).not.toBeInTheDocument()
    })
    // Empty state for sessions should appear
    expect(await screen.findByText('セッションがありません')).toBeInTheDocument()
  })
})
