import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ConnectionsPage } from '../ConnectionsPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
  info: ReturnType<typeof vi.fn>
}

const connectionsResponse = [
  { platform: 'note', status: 'connected', connected_at: '2026-06-01T10:00:00Z' },
  { platform: 'x', status: 'disconnected', connected_at: null },
  { platform: 'wordpress', status: 'disconnected', connected_at: null },
]

beforeEach(() => {
  mockApi.mockReset()
  mockedToast.error.mockReset()
  mockedToast.success.mockReset()
  mockedToast.info.mockReset()
})

// (a) List renders platforms with connected/disconnected badges
it('プラットフォーム一覧をバッジ付きで表示する', async () => {
  mockApi.mockResolvedValueOnce(connectionsResponse)
  renderWithRouter(<ConnectionsPage />)

  expect(await screen.findByText('note')).toBeInTheDocument()
  expect(screen.getByText('X (Twitter)')).toBeInTheDocument()
  expect(screen.getByText('WordPress')).toBeInTheDocument()

  const badges = screen.getAllByText('接続済み')
  expect(badges).toHaveLength(1)
  const disconnectedBadges = screen.getAllByText('未接続')
  expect(disconnectedBadges).toHaveLength(2)
})

// (b) Clicking 接続 posts to the right URL and shows the detail toast
it('接続ボタンで POST /api/publishing/connections/{platform}/login を叩き detail を toast に表示する', async () => {
  mockApi.mockResolvedValueOnce(connectionsResponse) // initial GET
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('X (Twitter)')

  mockApi.mockResolvedValueOnce({
    platform: 'x',
    status: 'login_started',
    detail: 'ブラウザウィンドウが開きました。X にログインしてください。',
  })

  // x comes before wordpress in the list; first 接続 button belongs to x
  const connectButtons = screen.getAllByRole('button', { name: /^接続$/ })
  await userEvent.click(connectButtons[0])

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/publishing/connections/x/login')
  })
  expect(mockedToast.info).toHaveBeenCalledWith('ブラウザウィンドウが開きました。X にログインしてください。')
})

// (c) Clicking 切断 calls DELETE and reloads
it('切断ボタンで DELETE /api/publishing/connections/{platform} を叩きリロードする', async () => {
  mockApi.mockResolvedValueOnce(connectionsResponse) // initial GET
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('note')

  const reloadedResponse = [
    { platform: 'note', status: 'disconnected', connected_at: null },
    { platform: 'x', status: 'disconnected', connected_at: null },
    { platform: 'wordpress', status: 'disconnected', connected_at: null },
  ]

  mockApi.mockResolvedValueOnce({ platform: 'note', cleared: true, status: 'disconnected' }) // DELETE
  mockApi.mockResolvedValueOnce(reloadedResponse) // reload GET (quiet)

  await userEvent.click(screen.getByRole('button', { name: /^切断$/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('DELETE', '/api/publishing/connections/note')
  })
  expect(mockedToast.success).toHaveBeenCalledWith('note の接続を切断しました。')

  await waitFor(() => {
    expect(screen.queryByText('接続済み')).not.toBeInTheDocument()
  })
})

// (d) Unsupported response shows the detail and does NOT start polling.
// We use fake timers to assert no interval-driven GET fires after the POST resolves.
describe('unsupported ステータスの場合、detail を toast に表示しポーリングを開始しない', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('wordpress の接続試行が unsupported のとき追加 GET を呼ばない', async () => {
    // Set up fake timers BEFORE rendering so that setInterval / setTimeout inside the
    // component are controlled. Use shouldAdvanceTime so that Promise microtasks still
    // resolve naturally; pair with advanceTimers so userEvent can progress.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) })

    mockApi.mockResolvedValueOnce(connectionsResponse) // initial GET
    renderWithRouter(<ConnectionsPage />)
    await screen.findByText('WordPress')

    mockApi.mockResolvedValueOnce({
      platform: 'wordpress',
      status: 'unsupported',
      detail: 'WordPress はブラウザセッション方式に対応していません。',
    })

    const connectButtons = screen.getAllByRole('button', { name: /^接続$/ })
    // wordpress is the last disconnected platform
    await user.click(connectButtons[connectButtons.length - 1])

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        'POST',
        '/api/publishing/connections/wordpress/login',
      )
    })
    expect(mockedToast.error).toHaveBeenCalledWith(
      'WordPress はブラウザセッション方式に対応していません。',
    )

    // Advance 10 seconds — no poller should have fired any additional GET calls
    vi.advanceTimersByTime(10_000)

    // Only the initial GET + POST login = 2 calls total; no polling GET
    expect(mockApi).toHaveBeenCalledTimes(2)
  })
})

// Happy path: login_started → ポーリングが connected を検知 → バッジ遷移 + ポーラー停止
describe('ログイン完了をポーリングで検知する', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('connected になったらバッジが切り替わりポーリングが止まる', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) })

    mockApi.mockResolvedValueOnce([{ platform: 'x', status: 'disconnected', connected_at: null }])
    renderWithRouter(<ConnectionsPage />)
    await screen.findByText('X (Twitter)')

    mockApi.mockResolvedValueOnce({
      platform: 'x',
      status: 'login_started',
      detail: 'ブラウザを起動しました。',
    })
    // 以後のポーリング GET は connected を返す
    mockApi.mockResolvedValue([
      { platform: 'x', status: 'connected', connected_at: '2026-06-12T13:00:00Z' },
    ])

    await user.click(screen.getByRole('button', { name: /^接続$/ }))
    expect(await screen.findByText('ログイン待機中')).toBeInTheDocument()

    // 1 tick 進める → ポーリング GET が connected を返しバッジが遷移する
    vi.advanceTimersByTime(3_100)
    expect(await screen.findByText('接続済み')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('ログイン待機中')).not.toBeInTheDocument()
    })

    // ポーラー停止後はさらに時間が経っても GET が増えない
    const callsAfterConnect = mockApi.mock.calls.length
    vi.advanceTimersByTime(10_000)
    expect(mockApi).toHaveBeenCalledTimes(callsAfterConnect)
  })
})

it('接続済みプラットフォームには切断ボタンのみ表示し接続ボタンは表示しない', async () => {
  mockApi.mockResolvedValueOnce([
    { platform: 'note', status: 'connected', connected_at: '2026-06-01T10:00:00Z' },
  ])
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('note')

  expect(screen.getByRole('button', { name: /^切断$/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^接続$/ })).not.toBeInTheDocument()
})

it('API エラー時に空状態エラーを表示する', async () => {
  mockApi.mockRejectedValueOnce(new Error('接続エラー'))
  renderWithRouter(<ConnectionsPage />)

  await waitFor(() => {
    expect(mockedToast.error).toHaveBeenCalledWith('接続エラー')
  })
  expect(await screen.findByText('接続情報の読み込みに失敗しました')).toBeInTheDocument()
})
