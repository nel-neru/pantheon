import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { InboxPage } from '../InboxPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const inboxResponse = {
  items: [
    {
      kind: 'publish',
      id: 'job-1',
      org_name: 'Note Sales',
      title: '朝活のコツ',
      category: 'external_action',
      priority: 'high',
      platform: 'note',
      scheduled_at: null,
      route: '/inbox',
    },
    {
      kind: 'proposal',
      id: 'prop-1',
      org_name: 'SNS Growth',
      title: 'テスト追加',
      category: 'quality',
      priority: 'medium',
      revenue_impact: 2,
      route: '/proposals?org=SNS Growth',
    },
  ],
  counts: { proposal: 1, handoff: 0, publish: 1, total: 2 },
}

beforeEach(() => {
  mockApi.mockReset()
  mockedToast.error.mockReset()
  mockedToast.success.mockReset()
})

it('集約された承認待ちを一覧表示する', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse)
  renderWithRouter(<InboxPage />)

  expect(await screen.findByText('朝活のコツ')).toBeInTheDocument()
  expect(screen.getByText('テスト追加')).toBeInTheDocument()
  expect(screen.getByText('Note Sales')).toBeInTheDocument()
})

it('収益インパクトの高い提案に「収益」バッジを表示する', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse)
  renderWithRouter(<InboxPage />)

  await screen.findByText('テスト追加')
  expect(screen.getByText('収益')).toBeInTheDocument()
})

it('投稿アイテムの「投稿」で publish-jobs/run を叩く', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse) // initial GET
  renderWithRouter(<InboxPage />)
  await screen.findByText('朝活のコツ')

  mockApi.mockResolvedValueOnce({ ok: true, job_id: 'job-1', platform: 'note' }) // run
  mockApi.mockResolvedValueOnce({ items: [], counts: { proposal: 0, handoff: 0, publish: 0, total: 0 } }) // reload

  await userEvent.click(screen.getByRole('button', { name: /^投稿$/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/publish-jobs/job-1/run')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})

it('投稿アイテムの「プレビュー」は dry_run=true を付与する', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse)
  renderWithRouter(<InboxPage />)
  await screen.findByText('朝活のコツ')

  mockApi.mockResolvedValueOnce({ ok: true, dry_run: true })
  mockApi.mockResolvedValueOnce(inboxResponse)

  await userEvent.click(screen.getByRole('button', { name: /プレビュー/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/publish-jobs/job-1/run?dry_run=true')
  })
})

it('承認待ちが無いとき空状態を表示する', async () => {
  mockApi.mockResolvedValueOnce({ items: [], counts: { proposal: 0, handoff: 0, publish: 0, total: 0 } })
  renderWithRouter(<InboxPage />)
  expect(await screen.findByText('承認待ちはありません')).toBeInTheDocument()
})

it('handed_off アイテムは「公開を確認」ボタンを表示し「投稿」「プレビュー」は非表示', async () => {
  const handedOffResponse = {
    items: [
      {
        kind: 'publish',
        id: 'job-ho',
        org_name: 'Note Sales',
        title: '公開確認テスト記事',
        category: 'external_action',
        priority: 'high',
        platform: 'note',
        scheduled_at: null,
        route: '/inbox',
        status: 'handed_off',
      },
    ],
    counts: { proposal: 0, handoff: 0, publish: 1, total: 1 },
  }
  mockApi.mockResolvedValueOnce(handedOffResponse)
  renderWithRouter(<InboxPage />)
  await screen.findByText('公開確認テスト記事')

  expect(screen.getByRole('button', { name: /公開を確認/ })).toBeInTheDocument()
  expect(screen.getByText('公開確認待ち')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^投稿$/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /プレビュー/ })).not.toBeInTheDocument()
})

it('handed_off アイテムの「公開を確認」クリックで /confirm を叩く', async () => {
  const handedOffResponse = {
    items: [
      {
        kind: 'publish',
        id: 'job-ho',
        org_name: 'Note Sales',
        title: '公開確認テスト記事',
        category: 'external_action',
        priority: 'high',
        platform: 'note',
        scheduled_at: null,
        route: '/inbox',
        status: 'handed_off',
      },
    ],
    counts: { proposal: 0, handoff: 0, publish: 1, total: 1 },
  }
  mockApi.mockResolvedValueOnce(handedOffResponse) // initial GET
  renderWithRouter(<InboxPage />)
  await screen.findByText('公開確認テスト記事')

  mockApi.mockResolvedValueOnce({ ok: true }) // confirm
  mockApi.mockResolvedValueOnce({ items: [], counts: { proposal: 0, handoff: 0, publish: 0, total: 0 } }) // reload

  await userEvent.click(screen.getByRole('button', { name: /公開を確認/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/publish-jobs/job-ho/confirm')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})
