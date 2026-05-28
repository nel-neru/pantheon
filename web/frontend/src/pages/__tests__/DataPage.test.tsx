import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { DataPage } from '../DataPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const historyItem = {
  id: 'history-1',
  goal: 'テストを増やす',
  org_name: 'alpha',
  result: 'テストを追加しました',
  timestamp: '2025-01-01T10:00:00.000Z',
}

const knowledgeFile = {
  path: 'guide.md',
  name: 'guide.md',
  size: 128,
  modified: 1735689600,
  extension: '.md',
}

const knowledgeDetail = {
  path: 'guide.md',
  name: 'guide.md',
  content: '# ガイド\nナレッジ本文',
  size: 128,
  modified: 1735689600,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('DataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows a loading state while history is loading', async () => {
    const request = deferred<typeof historyItem[]>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return request.promise
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    expect(screen.getByText('データを読み込み中…')).toBeInTheDocument()

    request.resolve([])
    await waitFor(() => {
      expect(screen.getByText('実行履歴がありません')).toBeInTheDocument()
    })
  })

  it('renders an empty state when there is no history', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return []
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    expect(await screen.findByText('実行履歴がありません')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '履歴をクリア' })).not.toBeInTheDocument()
  })

  it('shows an error toast when loading fails', async () => {
    mockApi.mockRejectedValue(new Error('history load failed'))

    renderWithRouter(<DataPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('history load failed')
    })
  })

  it('renders loaded history rows', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return [historyItem]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    expect(await screen.findByText('テストを増やす')).toBeInTheDocument()
    expect(screen.getByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('テストを追加しました')).toBeInTheDocument()
  })

  it('refreshes history when the reload button is clicked', async () => {
    const first: typeof historyItem[] = []
    const second: typeof historyItem[] = [historyItem]
    let callCount = 0

    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        callCount += 1
        return callCount === 1 ? first : second
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    expect(await screen.findByText('実行履歴がありません')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '再読み込み' }))

    expect(await screen.findByText('テストを増やす')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledTimes(2)
  })

  it('clears history after confirmation', async () => {
    let currentHistory = [historyItem]
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return currentHistory
      }
      if (method === 'DELETE' && path === '/api/goals/history') {
        currentHistory = []
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    expect(await screen.findByText('テストを増やす')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '履歴をクリア' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('履歴を削除しました。')
    })
    expect(screen.getByText('実行履歴がありません')).toBeInTheDocument()
  })

  it('switches to the knowledge tab and loads the file list', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return []
      }
      if (method === 'GET' && path === '/api/knowledge/files') {
        return { files: [knowledgeFile] }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    expect(await screen.findByText('実行履歴がありません')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'ナレッジ' }))

    expect(await screen.findByText('1 件のナレッジファイル')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guide\.md/ })).toBeInTheDocument()
  })

  it('shows file details when a knowledge file is clicked', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return []
      }
      if (method === 'GET' && path === '/api/knowledge/files') {
        return { files: [knowledgeFile] }
      }
      if (method === 'GET' && path === '/api/knowledge/files/guide.md') {
        return knowledgeDetail
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    expect(await screen.findByText('実行履歴がありません')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'ナレッジ' }))
    await user.click(await screen.findByRole('button', { name: /guide\.md/ }))

    expect(await screen.findByText(/ナレッジ本文/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '編集' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '削除' })).toBeInTheDocument()
  })
})
