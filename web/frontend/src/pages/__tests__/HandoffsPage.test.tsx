import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { HandoffsPage } from '../HandoffsPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const pendingHandoff = {
  handoff_id: 'handoff:abc12345',
  source_org: 'SNS Growth',
  target_org: 'Note Sales',
  kind: 'audience_signal',
  title: '検証済み需要: ChatGPT議事録',
  payload: { theme: 'ChatGPTで議事録自動化' },
  status: 'pending',
  priority: 'medium',
  note: '',
  policy_decision: 'human_required',
  policy_reason: 'ピア org 間の引き渡しは人間確認必須',
  consumed_ref: '',
  materialized_ref: '',
}

beforeEach(() => {
  mockApi.mockReset()
  mockedToast.error.mockReset()
  mockedToast.success.mockReset()
})

it('renders the page title and status filter', async () => {
  mockApi.mockResolvedValue([])
  renderWithRouter(<HandoffsPage />)
  expect(await screen.findByText('引き渡し（集客→販売→収益化）')).toBeInTheDocument()
  expect(screen.getByLabelText('ステータスフィルタ')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /更新/ })).toBeInTheDocument()
})

it('lists pending handoffs with localized labels', async () => {
  mockApi.mockResolvedValue([pendingHandoff])
  renderWithRouter(<HandoffsPage />)

  expect(await screen.findByText('検証済み需要: ChatGPT議事録')).toBeInTheDocument()
  expect(screen.getByText('SNS Growth')).toBeInTheDocument()
  expect(screen.getByText('Note Sales')).toBeInTheDocument()
  // kind is shown as a localized label
  expect(screen.getByText('集客シグナル')).toBeInTheDocument()
  // status is shown as Japanese
  expect(screen.getByText('承認待ち')).toBeInTheDocument()
  // policy reason is shown
  expect(screen.getByText('ピア org 間の引き渡しは人間確認必須')).toBeInTheDocument()
})

it('shows payload primitives in a definition list', async () => {
  mockApi.mockResolvedValue([pendingHandoff])
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')
  // The payload key 'theme' and its value are shown.
  expect(screen.getByText('theme')).toBeInTheDocument()
  expect(screen.getByText('ChatGPTで議事録自動化')).toBeInTheDocument()
})

describe('approve flow — requires ConfirmDialog confirmation', () => {
  it('opens ConfirmDialog on approve click, does NOT call API until confirmed', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    // Clicking approve should open the dialog, not call the API yet.
    await userEvent.click(screen.getByRole('button', { name: /承認＋本文生成/ }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/承認して本文を生成しますか？/)).toBeInTheDocument()
    // API should only have been called for the initial GET calls
    const postCalls = mockApi.mock.calls.filter(([method]) => method === 'POST')
    expect(postCalls).toHaveLength(0)
  })

  it('calls approve API and reloads after confirming in dialog', async () => {
    mockApi.mockResolvedValue([pendingHandoff]) // initial GETs (multiple calls for counts)
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    await userEvent.click(screen.getByRole('button', { name: /承認＋本文生成/ }))
    await screen.findByRole('dialog')

    // The POST approve response
    mockApi.mockResolvedValueOnce({
      ...pendingHandoff,
      status: 'approved',
      materialized: {
        proposal_id: 'p-1',
        org_name: 'Note Sales',
        title: '有料note企画ブリーフ',
        file_path: 'content/brief-note-abc12345.md',
      },
    })
    mockApi.mockResolvedValue([]) // reload after approve

    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /承認＋本文生成/ }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        'POST',
        '/api/handoffs/handoff%3Aabc12345/approve',
        { draft: true },
      )
    })
    expect(mockedToast.success).toHaveBeenCalled()
  })

  it('cancels approve dialog without calling API', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    await userEvent.click(screen.getByRole('button', { name: /承認＋本文生成/ }))
    await screen.findByRole('dialog')

    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /キャンセル/ }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    const postCalls = mockApi.mock.calls.filter(([method]) => method === 'POST')
    expect(postCalls).toHaveLength(0)
  })
})

describe('reject flow — requires ConfirmDialog confirmation', () => {
  it('opens ConfirmDialog on reject click, does NOT call API until confirmed', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    await userEvent.click(screen.getByRole('button', { name: /^却下$/ }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/却下しますか/)).toBeInTheDocument()
    const postCalls = mockApi.mock.calls.filter(([method]) => method === 'POST')
    expect(postCalls).toHaveLength(0)
  })

  it('calls reject API and reloads after confirming in dialog', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    await userEvent.click(screen.getByRole('button', { name: /^却下$/ }))
    await screen.findByRole('dialog')

    mockApi.mockResolvedValueOnce({ ...pendingHandoff, status: 'rejected' }) // POST reject
    mockApi.mockResolvedValue([]) // reload

    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /却下する/ }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/handoffs/handoff%3Aabc12345/reject')
    })
    expect(mockedToast.success).toHaveBeenCalledWith('却下しました。')
  })
})

describe('draft (本文のみ生成) flow', () => {
  it('generates draft and reloads the list on success', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    mockApi.mockResolvedValueOnce({
      handoff_id: pendingHandoff.handoff_id,
      proposal_id: 'p-9',
      org_name: 'Note Sales',
      title: '本文ドラフト: 有料note企画ブリーフ',
      file_path: 'content/draft-abc12345.md',
    })
    mockApi.mockResolvedValue([]) // reload after draft

    await userEvent.click(screen.getByRole('button', { name: /本文のみ生成/ }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/handoffs/handoff%3Aabc12345/draft')
    })
    expect(mockedToast.success).toHaveBeenCalled()
    // List should reload (a subsequent GET call).
    await waitFor(() => {
      const getCalls = mockApi.mock.calls.filter(([method]) => method === 'GET')
      expect(getCalls.length).toBeGreaterThan(1)
    })
  })

  it('shows error toast on draft failure without closing the card', async () => {
    mockApi.mockResolvedValue([pendingHandoff])
    renderWithRouter(<HandoffsPage />)
    await screen.findByText('検証済み需要: ChatGPT議事録')

    mockApi.mockRejectedValueOnce(new Error('生成に失敗しました'))

    await userEvent.click(screen.getByRole('button', { name: /本文のみ生成/ }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('生成に失敗しました')
    })
    // Card is still visible.
    expect(screen.getByText('検証済み需要: ChatGPT議事録')).toBeInTheDocument()
  })
})

it('shows an empty state with filter-appropriate message for pending', async () => {
  mockApi.mockResolvedValue([])
  renderWithRouter(<HandoffsPage />)
  expect(await screen.findByText('引き渡しがありません')).toBeInTheDocument()
  expect(screen.getByText(/SNS運用→note販売/)).toBeInTheDocument()
})

it('shows load error with retry button and does NOT show a toast', async () => {
  mockApi.mockRejectedValue(new Error('サーバーエラー'))
  renderWithRouter(<HandoffsPage />)

  expect(await screen.findByText('引き渡しの読み込みに失敗しました')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /再試行/ })).toBeInTheDocument()
  // Load failure must NOT trigger a toast.
  expect(mockedToast.error).not.toHaveBeenCalled()
})

it('retry button re-fetches handoffs', async () => {
  mockApi.mockRejectedValueOnce(new Error('初回失敗'))
  renderWithRouter(<HandoffsPage />)

  await screen.findByText('引き渡しの読み込みに失敗しました')

  mockApi.mockResolvedValue([pendingHandoff])
  await userEvent.click(screen.getByRole('button', { name: /再試行/ }))

  expect(await screen.findByText('検証済み需要: ChatGPT議事録')).toBeInTheDocument()
})

it('approve and reject buttons are disabled for non-pending handoffs', async () => {
  const approvedHandoff = { ...pendingHandoff, status: 'approved' }
  mockApi.mockResolvedValue([approvedHandoff])
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')

  expect(screen.getByRole('button', { name: /承認＋本文生成/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: /^却下$/ })).toBeDisabled()
})

it('draft button is disabled for rejected handoffs', async () => {
  const rejectedHandoff = { ...pendingHandoff, status: 'rejected' }
  mockApi.mockResolvedValue([rejectedHandoff])
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')

  expect(screen.getByRole('button', { name: /本文のみ生成/ })).toBeDisabled()
})

it('shows materialized_ref when present', async () => {
  const handoffWithRef = {
    ...pendingHandoff,
    status: 'approved',
    materialized_ref: 'proposal:abc123456789',
  }
  mockApi.mockResolvedValue([handoffWithRef])
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')

  expect(screen.getByText('生成済みドラフト:')).toBeInTheDocument()
  expect(screen.getByTitle('proposal:abc123456789')).toBeInTheDocument()
})

it('refresh button triggers a quiet reload', async () => {
  mockApi.mockResolvedValue([pendingHandoff])
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')

  const callsBefore = mockApi.mock.calls.length
  await userEvent.click(screen.getByRole('button', { name: /更新/ }))

  // At least one more GET call was made after clicking refresh.
  await waitFor(() => {
    expect(mockApi.mock.calls.length).toBeGreaterThan(callsBefore)
  })
})
