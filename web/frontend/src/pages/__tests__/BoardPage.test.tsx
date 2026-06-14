import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { BoardPage } from '../BoardPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const orgs = [
  { name: 'Acme' },
  { name: 'Beta' },
]

const tasks = [
  { id: 't1', type: 'analysis', org_name: 'Acme', description: 'Review repo', status: 'pending', priority: 5 },
  { id: 't2', type: 'manual', org_name: 'Acme', description: 'Deploy build', status: 'running', priority: 5 },
  { id: 't3', type: 'manual', org_name: 'Acme', description: 'Broken job', status: 'failed', priority: 5, error: 'boom' },
]

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

type TaskFixture = {
  id: string
  type: string
  org_name: string
  description: string
  status: string
  priority: number
  error?: string
}

function setupApi(taskList?: TaskFixture[]) {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path.startsWith('/api/tasks')) {
      return { tasks: taskList ?? [] }
    }
    if (method === 'GET' && path === '/api/organizations') return orgs
    throw new Error(`Unexpected request: ${method} ${path}`)
  })
}

describe('BoardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while the board is loading', async () => {
    const request = deferred<{ tasks: typeof tasks }>()
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path.startsWith('/api/tasks')) return request.promise
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<BoardPage />)
    expect(screen.getByText('作業ボードを読み込み中…')).toBeInTheDocument()

    request.resolve({ tasks: [] })
    await waitFor(() => {
      expect(screen.getAllByText(/該当なし|タスクがありません/).length).toBeGreaterThan(0)
    })
  })

  it('shows an error state when the board request fails', async () => {
    mockApi.mockRejectedValue(new Error('board load failed'))
    renderWithRouter(<BoardPage />)
    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('board load failed')
    })
    expect(await screen.findByText('作業ボードの読み込みに失敗しました')).toBeInTheDocument()
  })

  it('renders tasks grouped into kanban columns', async () => {
    setupApi(tasks)

    renderWithRouter(<BoardPage />)
    expect(await screen.findByText('Review repo')).toBeInTheDocument()
    expect(screen.getByText('Deploy build')).toBeInTheDocument()
    expect(screen.getByText('Broken job')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('renders 失敗 column (not レビュー) for failed tasks', async () => {
    setupApi(tasks)

    renderWithRouter(<BoardPage />)
    await screen.findByText('Review repo')
    // Column header must say 失敗, not レビュー
    expect(screen.getByText('失敗')).toBeInTheDocument()
    expect(screen.queryByText('レビュー')).not.toBeInTheDocument()
  })

  it('shows cancel button only for pending tasks, not running', async () => {
    setupApi(tasks)

    renderWithRouter(<BoardPage />)
    await screen.findByText('Review repo')

    // pending task should have cancel button
    const pendingCard = (screen.getByText('Review repo').closest('.board-card') as HTMLElement)
    expect(within(pendingCard).getByLabelText('タスクをキャンセル')).toBeInTheDocument()

    // running task should NOT have cancel button
    const runningCard = (screen.getByText('Deploy build').closest('.board-card') as HTMLElement)
    expect(within(runningCard).queryByLabelText('タスクをキャンセル')).not.toBeInTheDocument()
  })

  it('opens a ConfirmDialog before cancelling a pending task', async () => {
    const calls: Array<[string, string]> = []
    mockApi.mockImplementation(async (method: string, path: string) => {
      calls.push([method, path])
      if (method === 'GET' && path.startsWith('/api/tasks')) return { tasks }
      if (method === 'GET' && path === '/api/organizations') return orgs
      if (method === 'DELETE' && path.startsWith('/api/tasks/')) return {}
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<BoardPage />)
    await screen.findByText('Review repo')

    // Click the cancel button on the pending task
    const pendingCard = (screen.getByText('Review repo').closest('.board-card') as HTMLElement)
    await user.click(within(pendingCard).getByLabelText('タスクをキャンセル'))

    // ConfirmDialog should appear — not yet deleted
    expect(await screen.findByText('タスクをキャンセルしますか？')).toBeInTheDocument()
    expect(calls.some(([m]) => m === 'DELETE')).toBe(false)

    // Confirm the action
    await user.click(screen.getByRole('button', { name: 'キャンセルする' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('タスクをキャンセルしました。')
    })
    expect(calls.some(([m, p]) => m === 'DELETE' && p.startsWith('/api/tasks/'))).toBe(true)
  })

  it('dismissing the ConfirmDialog does not cancel the task', async () => {
    const deleteCalls: string[] = []
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path.startsWith('/api/tasks')) return { tasks }
      if (method === 'GET' && path === '/api/organizations') return orgs
      if (method === 'DELETE' && path.startsWith('/api/tasks/')) {
        deleteCalls.push(path)
        return {}
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<BoardPage />)
    await screen.findByText('Review repo')

    const pendingCard = (screen.getByText('Review repo').closest('.board-card') as HTMLElement)
    await user.click(within(pendingCard).getByLabelText('タスクをキャンセル'))

    // Dialog appears
    expect(await screen.findByText('タスクをキャンセルしますか？')).toBeInTheDocument()

    // Click cancel button (close dialog without confirming)
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => {
      expect(screen.queryByText('タスクをキャンセルしますか？')).not.toBeInTheDocument()
    })
    expect(deleteCalls).toHaveLength(0)
  })

  it('creates a task through the new task form using select for org and type', async () => {
    const calls: Array<[string, string, unknown]> = []
    mockApi.mockImplementation(async (method: string, path: string, body?: unknown) => {
      calls.push([method, path, body])
      if (method === 'GET' && path.startsWith('/api/tasks')) return { tasks: [] }
      if (method === 'GET' && path === '/api/organizations') return orgs
      if (method === 'POST' && path === '/api/tasks') return { id: 'new' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<BoardPage />)
    await waitFor(() => expect(screen.getAllByText(/該当なし|タスクがありません/).length).toBeGreaterThan(0))

    await user.click(screen.getByRole('button', { name: '新規タスク' }))

    // Fill description (textarea)
    await user.type(screen.getByLabelText('タスクの説明'), 'New work item')

    // Select org from dropdown
    await user.selectOptions(screen.getByLabelText('組織名'), 'Acme')

    // Submit the form
    await user.click(screen.getByRole('button', { name: '起票' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('タスクを起票しました。')
    })
    expect(calls.some(([m, p]) => m === 'POST' && p === '/api/tasks')).toBe(true)
  })

  it('shows cancelled tasks with キャンセル済 badge in 完了 column', async () => {
    const cancelledTask = {
      id: 't5',
      type: 'manual',
      org_name: 'Acme',
      description: 'Cancelled task',
      status: 'cancelled',
      priority: 3,
    }
    setupApi([cancelledTask])

    renderWithRouter(<BoardPage />)
    await screen.findByText('Cancelled task')

    // The badge label should appear
    expect(screen.getByText('キャンセル済')).toBeInTheDocument()
  })

  it('shows stats total count when different from displayed count', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path.startsWith('/api/tasks')) {
        return { tasks, stats: { total: 500, pending: 1, running: 1, done: 498, failed: 0 } }
      }
      if (method === 'GET' && path === '/api/organizations') return orgs
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<BoardPage />)
    await screen.findByText('Review repo')

    // Should show "X 件中 Y 件表示" since stats.total > tasks.length
    expect(screen.getByText(/500 件中 3 件表示/)).toBeInTheDocument()
  })

  it('shows quiet reload indicator (no full board spinner) on re-fetch', async () => {
    setupApi(tasks)
    const user = userEvent.setup()
    renderWithRouter(<BoardPage />)

    await screen.findByText('Review repo')
    // Board is loaded; now click refresh
    await user.click(screen.getByRole('button', { name: '再読み込み' }))

    // Board content should still be visible (no full spinner overlay)
    expect(screen.getByText('Review repo')).toBeInTheDocument()
    // Full loading card should not appear
    expect(screen.queryByText('作業ボードを読み込み中…')).not.toBeInTheDocument()
  })
})
