import { screen, waitFor } from '@testing-library/react'
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

describe('BoardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while the board is loading', async () => {
    const request = deferred<{ tasks: typeof tasks }>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path.startsWith('/api/tasks')) return request.promise
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<BoardPage />)
    expect(screen.getByText('作業ボードを読み込み中…')).toBeInTheDocument()

    request.resolve({ tasks: [] })
    await waitFor(() => {
      expect(screen.getAllByText('なし').length).toBeGreaterThan(0)
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
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path.startsWith('/api/tasks')) return { tasks }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<BoardPage />)
    expect(await screen.findByText('Review repo')).toBeInTheDocument()
    expect(screen.getByText('Deploy build')).toBeInTheDocument()
    expect(screen.getByText('Broken job')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('creates a task through the new task form', async () => {
    const calls: Array<[string, string, unknown]> = []
    mockApi.mockImplementation(async (method, path, body) => {
      calls.push([method, path, body])
      if (method === 'GET' && path.startsWith('/api/tasks')) return { tasks: [] }
      if (method === 'POST' && path === '/api/tasks') return { id: 'new' }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<BoardPage />)
    await waitFor(() => expect(screen.getAllByText('なし').length).toBeGreaterThan(0))

    await user.click(screen.getByRole('button', { name: '新規タスク' }))
    await user.type(screen.getByLabelText('タスクの説明'), 'New work item')
    await user.type(screen.getByLabelText('組織名'), 'Acme')
    await user.click(screen.getByRole('button', { name: '起票' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('タスクを起票しました。')
    })
    expect(calls.some(([m, p]) => m === 'POST' && p === '/api/tasks')).toBe(true)
  })
})
