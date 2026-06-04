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

  it('renders session and agent data', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/sessions') return { sessions: [session] }
      if (method === 'GET' && path === '/api/sessions/runtime') return runtime
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<SessionsPage />)
    expect(await screen.findByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Greeter')).toBeInTheDocument()
    expect(screen.getByText('agent:greeter')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
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
})
