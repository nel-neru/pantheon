import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { AnalyzePage } from '../AnalyzePage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const organizations = [{ name: 'alpha' }, { name: 'beta' }]

describe('AnalyzePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('renders the form and empty log state', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AnalyzePage />)

    expect(await screen.findByLabelText('対象組織')).toHaveValue('alpha')
    expect(screen.getByPlaceholderText('任意の上限')).toBeInTheDocument()
    expect(screen.getByText('まだ分析アクティビティがありません')).toBeInTheDocument()
  })

  it('shows a running state while analysis is in progress', async () => {
    let onEvent: ((event: Record<string, unknown>) => void) | undefined
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })
    mockStreamSSE.mockImplementation((path, body, eventHandler) => {
      onEvent = eventHandler
      return new AbortController()
    })

    const user = userEvent.setup()
    renderWithRouter(<AnalyzePage />)

    expect(await screen.findByLabelText('対象組織')).toHaveValue('alpha')
    await user.click(screen.getByRole('button', { name: '分析を実行' }))

    expect(screen.getByRole('button', { name: '実行中' })).toBeDisabled()

    onEvent?.({ type: 'progress', content: '解析中' })
    expect(await screen.findByText('解析中')).toBeInTheDocument()
  })

  it('shows a distinct empty state when no organizations exist', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AnalyzePage />)

    expect(await screen.findByText('分析対象の組織がありません')).toBeInTheDocument()
  })

  it('shows an error toast and inline error state when organization loading fails', async () => {
    mockApi.mockRejectedValue(new Error('org load failed'))

    renderWithRouter(<AnalyzePage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('org load failed')
    })
    expect(await screen.findByText('組織の読み込みに失敗しました')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })

  it('runs analysis and renders streamed results', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })
    mockStreamSSE.mockImplementation((path, body, onEvent) => {
      expect(path).toBe('/api/analyze/stream')
      expect(body).toEqual({ org_name: 'beta', max_files: 25 })
      onEvent({ type: 'start', org_name: 'beta' })
      onEvent({ type: 'proposal', title: 'Extract hook' })
      onEvent({ type: 'done', org_name: 'beta', files_reviewed: 12, proposals_generated: 3 })
      return new AbortController()
    })

    const user = userEvent.setup()
    renderWithRouter(<AnalyzePage />)

    expect(await screen.findByLabelText('対象組織')).toHaveValue('alpha')
    await user.selectOptions(screen.getByLabelText('対象組織'), 'beta')
    await user.type(screen.getByLabelText('最大ファイル数'), '25')
    await user.click(screen.getByRole('button', { name: '分析を実行' }))

    expect(await screen.findByText('beta の分析を開始します')).toBeInTheDocument()
    expect(screen.getByText('提案を生成しました: Extract hook')).toBeInTheDocument()
    expect(screen.getByText('分析結果')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(mockedToast.success).toHaveBeenCalledWith('分析が完了しました。')
  })

  it('shows a stream error in the log and toast', async () => {
    let onError: ((error: Error) => void) | undefined
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      throw new Error(`Unexpected request: ${method} ${path}`)
    })
    mockStreamSSE.mockImplementation((path, body, onEvent, onDone, streamError) => {
      onError = streamError
      return new AbortController()
    })

    const user = userEvent.setup()
    renderWithRouter(<AnalyzePage />)

    expect(await screen.findByLabelText('対象組織')).toHaveValue('alpha')
    await user.click(screen.getByRole('button', { name: '分析を実行' }))
    onError?.(new Error('stream failed'))

    expect(await screen.findByText('stream failed')).toBeInTheDocument()
    expect(mockedToast.error).toHaveBeenCalledWith('stream failed')
  })
})
