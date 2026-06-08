import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
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

it('lists pending handoffs and approves with materialization toast', async () => {
  mockApi.mockResolvedValueOnce([pendingHandoff]) // initial GET
  renderWithRouter(<HandoffsPage />)

  expect(await screen.findByText('検証済み需要: ChatGPT議事録')).toBeInTheDocument()
  expect(screen.getByText('SNS Growth')).toBeInTheDocument()
  expect(screen.getByText('Note Sales')).toBeInTheDocument()

  // approve → POST returns materialized; then a reload GET
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
  mockApi.mockResolvedValueOnce([]) // reload after approve

  await userEvent.click(screen.getByRole('button', { name: /承認/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/handoffs/handoff%3Aabc12345/approve')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})

it('generates a body draft via the 本文生成 button', async () => {
  mockApi.mockResolvedValueOnce([pendingHandoff]) // initial GET
  renderWithRouter(<HandoffsPage />)
  await screen.findByText('検証済み需要: ChatGPT議事録')

  mockApi.mockResolvedValueOnce({
    handoff_id: pendingHandoff.handoff_id,
    proposal_id: 'p-9',
    org_name: 'Note Sales',
    title: '本文ドラフト: 有料note企画ブリーフ',
    file_path: 'content/draft-abc12345.md',
  })

  await userEvent.click(screen.getByRole('button', { name: /本文生成/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/handoffs/handoff%3Aabc12345/draft')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})

it('shows an empty state when there are no handoffs', async () => {
  mockApi.mockResolvedValueOnce([])
  renderWithRouter(<HandoffsPage />)
  expect(await screen.findByText('引き渡しがありません')).toBeInTheDocument()
})
