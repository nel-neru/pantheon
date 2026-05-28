import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { GoalsPage } from '../GoalsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const historyItem = {
  goal: '品質を改善する',
  result: '改善提案を作成しました',
  timestamp: '2025-01-01T10:00:00.000Z',
}

const organizations = [{ name: 'alpha' }, { name: 'beta' }]

describe('GoalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('renders empty states when there are no logs or history entries', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<GoalsPage />)

    expect(await screen.findByText('まだ実行アクティビティがありません')).toBeInTheDocument()
    expect(screen.getByText('まだゴール履歴がありません')).toBeInTheDocument()
  })

  it('shows an error toast when history loading fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') {
        throw new Error('history load failed')
      }
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<GoalsPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('history load failed')
    })
  })

  it('validates that a goal is entered before execution', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return []
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    expect(await screen.findByText('まだ実行アクティビティがありません')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(mockedToast.error).toHaveBeenCalledWith('実行前にゴールを入力してください。')
  })

  it('shows a running state and renders streamed goal results', async () => {
    let historyCalls = 0
    let onEvent: ((event: Record<string, unknown>) => void) | undefined
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/goals/history') {
        historyCalls += 1
        return historyCalls === 1 ? [] : [historyItem]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })
    mockStreamSSE.mockImplementation((path, body, eventHandler) => {
      expect(path).toBe('/api/goals/stream')
      expect(body).toEqual({ goal_text: 'テストカバレッジを上げる', org_name: 'beta' })
      onEvent = eventHandler
      return new AbortController()
    })

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    expect(await screen.findByLabelText('ゴールテキスト')).toBeInTheDocument()
    await user.type(screen.getByLabelText('ゴールテキスト'), 'テストカバレッジを上げる')
    await user.selectOptions(screen.getByLabelText('対象組織'), 'beta')
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(screen.getByRole('button', { name: '実行中' })).toBeDisabled()

    onEvent?.({ type: 'start', org_name: 'beta' })
    onEvent?.({ type: 'result', result: '12 件のテストを追加しました。' })
    onEvent?.({ type: 'done', content: '完了しました' })

    expect(await screen.findByText('beta のゴール実行を開始します')).toBeInTheDocument()
    expect(screen.getAllByText('結果').length).toBeGreaterThan(0)
    expect(screen.getAllByText('12 件のテストを追加しました。').length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(screen.getByText('品質を改善する')).toBeInTheDocument()
    })
    expect(mockedToast.success).toHaveBeenCalledWith('ゴールの実行が完了しました。')
  })

  it('renders existing history rows', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/goals/history') return [historyItem]
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<GoalsPage />)

    expect(await screen.findByText('品質を改善する')).toBeInTheDocument()
    expect(screen.getByText('改善提案を作成しました')).toBeInTheDocument()
  })
})
