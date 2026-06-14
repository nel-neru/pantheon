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

// (b) Clicking 接続 posts to the right URL and shows the detail toast (with browser-open hint)
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
  // Toast includes the detail and the browser-open hint
  expect(mockedToast.info).toHaveBeenCalledWith(
    expect.stringContaining('ブラウザウィンドウが開きました。X にログインしてください。'),
  )
})

// login_in_progress is treated the same as login_started (merged branch)
it('login_in_progress でも toast を表示しポーリングを開始する', async () => {
  mockApi.mockResolvedValueOnce([{ platform: 'x', status: 'disconnected', connected_at: null }])
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('X (Twitter)')

  mockApi.mockResolvedValueOnce({
    platform: 'x',
    status: 'login_in_progress',
    detail: 'すでにログイン中です。',
  })

  await userEvent.click(screen.getByRole('button', { name: /^接続$/ }))

  await waitFor(() => {
    expect(mockedToast.info).toHaveBeenCalled()
  })
})

// (c) Clicking 切断 opens ConfirmDialog, confirming calls DELETE and reloads
it('切断ボタンで確認ダイアログが開き、確定すると DELETE /api/publishing/connections/{platform} を叩きリロードする', async () => {
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

  // First click opens the ConfirmDialog — DELETE must NOT be called yet
  await userEvent.click(screen.getByRole('button', { name: /^切断$/ }))

  // ConfirmDialog should be open (confirm button visible)
  const confirmBtn = await screen.findByRole('button', { name: '切断する' })
  expect(confirmBtn).toBeInTheDocument()
  expect(mockApi).not.toHaveBeenCalledWith('DELETE', expect.any(String))

  // Confirm the destructive action
  await userEvent.click(confirmBtn)

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('DELETE', '/api/publishing/connections/note')
  })
  expect(mockedToast.success).toHaveBeenCalledWith('note の接続を切断しました。')

  await waitFor(() => {
    expect(screen.queryByText('接続済み')).not.toBeInTheDocument()
  })
})

// Cancelling the ConfirmDialog does NOT call DELETE
it('切断確認ダイアログをキャンセルすると DELETE を呼ばない', async () => {
  mockApi.mockResolvedValueOnce([
    { platform: 'note', status: 'connected', connected_at: '2026-06-01T10:00:00Z' },
  ])
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('note')

  await userEvent.click(screen.getByRole('button', { name: /^切断$/ }))

  // ConfirmDialog is open
  expect(await screen.findByRole('button', { name: '切断する' })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /キャンセル/ }))

  await waitFor(() => {
    expect(screen.queryByRole('button', { name: '切断する' })).not.toBeInTheDocument()
  })
  // Only the initial GET — no DELETE
  expect(mockApi).toHaveBeenCalledTimes(1)
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
    expect(await screen.findByText('別ウィンドウでログインしてください')).toBeInTheDocument()

    // 1 tick 進める → ポーリング GET が connected を返しバッジが遷移する
    vi.advanceTimersByTime(3_100)
    expect(await screen.findByText('接続済み')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('別ウィンドウでログインしてください')).not.toBeInTheDocument()
    })

    // ポーラー停止後はさらに時間が経っても GET が増えない
    const callsAfterConnect = mockApi.mock.calls.length
    vi.advanceTimersByTime(10_000)
    expect(mockApi).toHaveBeenCalledTimes(callsAfterConnect)
  })

  it('120秒タイムアウトでポーリングが停止し toast.info を表示する', async () => {
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
    // ポーリング GET は常に disconnected を返す（タイムアウトまで接続されない）
    mockApi.mockResolvedValue([{ platform: 'x', status: 'disconnected', connected_at: null }])

    await user.click(screen.getByRole('button', { name: /^接続$/ }))
    expect(await screen.findByText('別ウィンドウでログインしてください')).toBeInTheDocument()

    // タイムアウト到達（120秒）
    vi.advanceTimersByTime(120_000)

    await waitFor(() => {
      expect(screen.queryByText('別ウィンドウでログインしてください')).not.toBeInTheDocument()
    })
    expect(mockedToast.info).toHaveBeenCalledWith(
      expect.stringContaining('ログインを確認できませんでした'),
    )
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

it('API エラー時に空状態エラーを表示する（toast は出さない）', async () => {
  mockApi.mockRejectedValueOnce(new Error('接続エラー'))
  renderWithRouter(<ConnectionsPage />)

  expect(await screen.findByText('接続情報の読み込みに失敗しました')).toBeInTheDocument()
  // 初回ロード失敗は UI に表示するのみ。toast.error による二重通知は行わない。
  expect(mockedToast.error).not.toHaveBeenCalled()
})

it('空のプラットフォームリスト時に案内と更新ボタンを表示する', async () => {
  mockApi.mockResolvedValueOnce([])
  renderWithRouter(<ConnectionsPage />)

  expect(await screen.findByText('接続先プラットフォームがありません')).toBeInTheDocument()
  expect(screen.getByText('サーバー設定を確認するか、更新してください。')).toBeInTheDocument()
  // 更新ボタンが空状態にある
  const updateButtons = screen.getAllByRole('button', { name: /更新/ })
  expect(updateButtons.length).toBeGreaterThanOrEqual(1)
})

it('接続日時を formatDateTime でフォーマットして表示する', async () => {
  mockApi.mockResolvedValueOnce([
    { platform: 'note', status: 'connected', connected_at: '2026-06-01T10:00:00Z' },
  ])
  renderWithRouter(<ConnectionsPage />)
  await screen.findByText('note')

  // formatDateTime は ja-JP ロケールの日時文字列を返す（生ISO表示ではない）
  const dateText = screen.getByText(/接続日時:/)
  expect(dateText.textContent).not.toContain('2026-06-01T') // 生ISO表示でない
  expect(dateText.textContent).toMatch(/2026/) // 年が含まれる
})
