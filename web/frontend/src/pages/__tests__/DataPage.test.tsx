import { screen, waitFor, within } from '@testing-library/react'
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
    // window.confirm should NOT be called — all destructive operations go through ConfirmDialog
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
    // clear button is hidden when history is empty (AsyncBoundary shows empty state, not children)
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

  it('normalizes legacy history rows that still use summary fields', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return [
          {
            goal_text: '品質を改善する',
            summary: '改善提案を作成しました',
            organization: 'beta',
            created_at: '2025-01-02T10:00:00.000Z',
          },
        ]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    expect(await screen.findByText('品質を改善する')).toBeInTheDocument()
    expect(screen.getByText('beta')).toBeInTheDocument()
    expect(screen.getByText('改善提案を作成しました')).toBeInTheDocument()
  })

  it('refreshes history when the refresh button is clicked', async () => {
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

    // C038: ボタン呼称は「更新」に統一
    await user.click(screen.getByRole('button', { name: '更新' }))

    expect(await screen.findByText('テストを増やす')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledTimes(2)
  })

  it('shows history success/failure badge when success field is present', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return [
          { ...historyItem, success: true },
          { ...historyItem, id: 'history-2', goal: '別のゴール', success: false },
        ]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    expect(await screen.findByText('成功')).toBeInTheDocument()
    expect(screen.getByText('失敗')).toBeInTheDocument()
  })

  it('clears history via ConfirmDialog (no window.confirm)', async () => {
    // Verify window.confirm is NOT called for this destructive operation
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

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

    // Click the clear button — this should open ConfirmDialog, not window.confirm
    await user.click(screen.getByRole('button', { name: '履歴をクリア' }))

    // ConfirmDialog should be open
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('履歴をすべて削除しますか？')).toBeInTheDocument()

    // window.confirm must NOT have been called
    expect(confirmSpy).not.toHaveBeenCalled()

    // Confirm in the dialog
    await user.click(screen.getByRole('button', { name: /件を削除/ }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('履歴を削除しました。')
    })
    expect(screen.getByText('実行履歴がありません')).toBeInTheDocument()

    confirmSpy.mockRestore()
  })

  it('cancels clear history when dialog is cancelled', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        return [historyItem]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    expect(await screen.findByText('テストを増やす')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '履歴をクリア' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Cancel the dialog
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    // History should still be there
    expect(screen.getByText('テストを増やす')).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalledWith('DELETE', '/api/goals/history')
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

    await user.click(screen.getByRole('tab', { name: 'ナレッジ' }))

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

    await user.click(screen.getByRole('tab', { name: 'ナレッジ' }))
    await user.click(await screen.findByRole('button', { name: /guide\.md/ }))

    expect(await screen.findByText(/ナレッジ本文/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '編集' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '削除' })).toBeInTheDocument()
  })

  it('deletes a file via ConfirmDialog (no window.confirm)', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    let filesResponse = { files: [knowledgeFile] }
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/knowledge/files') return filesResponse
      if (method === 'GET' && path === '/api/knowledge/files/guide.md') return knowledgeDetail
      if (method === 'DELETE' && path === '/api/knowledge/files/guide.md') {
        filesResponse = { files: [] }
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    await user.click(await screen.findByRole('tab', { name: 'ナレッジ' }))
    await user.click(await screen.findByRole('button', { name: /guide\.md/ }))
    expect(await screen.findByRole('button', { name: '削除' })).toBeInTheDocument()

    // Click delete — should open ConfirmDialog
    await user.click(screen.getByRole('button', { name: '削除' }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('ファイルを削除しますか？')).toBeInTheDocument()
    expect(confirmSpy).not.toHaveBeenCalled()

    // Confirm deletion
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: '削除' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('ファイルを削除しました。')
    })

    confirmSpy.mockRestore()
  })

  it('save button is disabled when content has not changed', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/knowledge/files') return { files: [knowledgeFile] }
      if (method === 'GET' && path === '/api/knowledge/files/guide.md') return knowledgeDetail
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    await user.click(await screen.findByRole('tab', { name: 'ナレッジ' }))
    await user.click(await screen.findByRole('button', { name: /guide\.md/ }))
    await user.click(await screen.findByRole('button', { name: '編集' }))

    // Save should be disabled when content hasn't changed
    const saveBtn = screen.getByRole('button', { name: '保存' })
    expect(saveBtn).toBeDisabled()
  })

  it('create dialog resets form state when cancelled', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/knowledge/files') return { files: [knowledgeFile] }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    await user.click(await screen.findByRole('tab', { name: 'ナレッジ' }))
    expect(await screen.findByText('1 件のナレッジファイル')).toBeInTheDocument()

    // Open create dialog
    await user.click(screen.getByRole('button', { name: '新規作成' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Type something into the filename input
    const input = screen.getByLabelText('ファイル名')
    await user.type(input, 'test.md')
    expect(input).toHaveValue('test.md')

    // Cancel — dialog closes and form is reset
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // Re-open — input should be empty
    await user.click(screen.getByRole('button', { name: '新規作成' }))
    const input2 = screen.getByLabelText('ファイル名')
    expect(input2).toHaveValue('')
  })

  it('shows inline validation error for invalid file names', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/knowledge/files') return { files: [] }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<DataPage />)

    await user.click(await screen.findByRole('tab', { name: 'ナレッジ' }))
    await user.click(await screen.findByRole('button', { name: '新規作成' }))

    const input = screen.getByLabelText('ファイル名')
    await user.type(input, '../evil.md')

    await user.click(screen.getByRole('button', { name: '作成' }))

    expect(await screen.findByText('パスセパレータや ".." は使用できません。')).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalledWith('POST', '/api/knowledge/files', expect.anything())
  })

  it('uses the Tabs component with correct ARIA role for tabs', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<DataPage />)

    await screen.findByText('実行履歴がありません')

    // Tabs rendered with role=tab via the shared Tabs component
    expect(screen.getByRole('tab', { name: 'ゴール履歴' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'ナレッジ' })).toBeInTheDocument()
  })
})
