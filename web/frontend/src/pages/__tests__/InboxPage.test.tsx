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

it('投稿アイテムの「投稿」は確認ダイアログ経由でのみ publish-jobs/run を叩く', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse) // initial GET
  renderWithRouter(<InboxPage />)
  await screen.findByText('朝活のコツ')

  // 「投稿」を押すと確認ダイアログが開くだけで、まだ外部投稿はしない（安全ゲート）。
  await userEvent.click(screen.getByRole('button', { name: /^投稿$/ }))
  const confirmBtn = await screen.findByRole('button', { name: '投稿する' })
  expect(mockApi).toHaveBeenCalledTimes(1) // GET のみ＝run は未実行

  mockApi.mockResolvedValueOnce({ ok: true, job_id: 'job-1', platform: 'note' }) // run
  mockApi.mockResolvedValueOnce({ items: [], counts: { proposal: 0, handoff: 0, publish: 0, total: 0 } }) // reload

  await userEvent.click(confirmBtn)

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

  await userEvent.click(screen.getByRole('button', { name: /公開を確認/ }))
  const confirmBtn = await screen.findByRole('button', { name: '公開を確定' })
  expect(mockApi).toHaveBeenCalledTimes(1) // GET のみ＝confirm は未実行

  mockApi.mockResolvedValueOnce({ ok: true }) // confirm
  mockApi.mockResolvedValueOnce({ items: [], counts: { proposal: 0, handoff: 0, publish: 0, total: 0 } }) // reload

  await userEvent.click(confirmBtn)

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/publish-jobs/job-ho/confirm')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})

// ── スタジオ導線テスト（C020） ──────────────────────────────────────────────────

it('content_asset カテゴリの提案に「スタジオで整える」ボタンを表示する', async () => {
  mockApi.mockResolvedValueOnce({
    items: [
      {
        kind: 'proposal',
        id: 'prop-ca',
        org_name: 'SNS Growth',
        title: 'SNS投稿下書き',
        category: 'content_asset',
        priority: 'medium',
        route: '/proposals?org=SNS Growth',
      },
    ],
    counts: { proposal: 1, handoff: 0, publish: 0, human_task: 0, total: 1 },
  })
  renderWithRouter(<InboxPage />)
  await screen.findByText('SNS投稿下書き')
  expect(screen.getByRole('button', { name: /スタジオで整える/ })).toBeInTheDocument()
})

it('quality カテゴリの提案には「スタジオで整える」ボタンを表示しない', async () => {
  mockApi.mockResolvedValueOnce(inboxResponse) // has quality proposal
  renderWithRouter(<InboxPage />)
  await screen.findByText('テスト追加')
  expect(screen.queryByRole('button', { name: /スタジオで整える/ })).not.toBeInTheDocument()
})

it('「スタジオで整える」クリックで proposals API を呼ぶ（content_asset 提案）', async () => {
  mockApi.mockResolvedValueOnce({
    items: [
      {
        kind: 'proposal',
        id: 'prop-ca',
        org_name: 'SNS Growth',
        title: 'SNS投稿下書き',
        category: 'content_asset',
        priority: 'medium',
        route: '/proposals?org=SNS Growth',
      },
    ],
    counts: { proposal: 1, handoff: 0, publish: 0, human_task: 0, total: 1 },
  })
  // proposals list response
  mockApi.mockResolvedValueOnce([
    {
      id: 'prop-ca',
      title: 'SNS投稿下書き',
      category: 'content_asset',
      intervention_spec: { content: 'これがSNS投稿本文', mode: 'create' },
    },
  ])
  renderWithRouter(<InboxPage />)
  await screen.findByText('SNS投稿下書き')

  await userEvent.click(screen.getByRole('button', { name: /スタジオで整える/ }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith(
      'GET',
      '/api/organizations/SNS%20Growth/proposals',
    )
  })
})

it('本文が無い提案の「スタジオで整える」クリックでエラー toast を表示する', async () => {
  mockApi.mockResolvedValueOnce({
    items: [
      {
        kind: 'proposal',
        id: 'prop-ca-empty',
        org_name: 'SNS Growth',
        title: '本文なし下書き',
        category: 'content_asset',
        priority: 'medium',
        route: '/proposals?org=SNS Growth',
      },
    ],
    counts: { proposal: 1, handoff: 0, publish: 0, human_task: 0, total: 1 },
  })
  // proposal with no content
  mockApi.mockResolvedValueOnce([
    {
      id: 'prop-ca-empty',
      title: '本文なし下書き',
      category: 'content_asset',
      intervention_spec: null,
    },
  ])
  renderWithRouter(<InboxPage />)
  await screen.findByText('本文なし下書き')

  await userEvent.click(screen.getByRole('button', { name: /スタジオで整える/ }))

  await waitFor(() => {
    expect(mockedToast.error).toHaveBeenCalledWith(
      expect.stringContaining('本文が含まれていません'),
    )
  })
})

it('handoff アイテムにも「スタジオで整える」ボタンを表示する', async () => {
  mockApi.mockResolvedValueOnce({
    items: [
      {
        kind: 'handoff',
        id: 'hnd-1',
        org_name: 'Note Sales',
        title: '記事ハンドオフ',
        category: 'cross_org_handoff',
        priority: 'medium',
        route: '/handoffs',
      },
    ],
    counts: { proposal: 0, handoff: 1, publish: 0, human_task: 0, total: 1 },
  })
  renderWithRouter(<InboxPage />)
  await screen.findByText('記事ハンドオフ')
  expect(screen.getByRole('button', { name: /スタジオで整える/ })).toBeInTheDocument()
})

it('human_task は却下が無く、「完了」を確認ダイアログ経由で叩く（C006）', async () => {
  mockApi.mockResolvedValueOnce({
    items: [
      {
        kind: 'human_task',
        id: 'human:1',
        org_name: 'SNS',
        title: 'X にログイン',
        category: 'account_setup',
        priority: 'high',
        ref: '',
        created_at: '2026-06-14T00:00:00Z',
        route: '/human-tasks',
      },
    ],
    counts: { proposal: 0, handoff: 0, publish: 0, human_task: 1, total: 1 },
  })
  renderWithRouter(<InboxPage />)
  await screen.findByText('X にログイン')

  // 人間タスクには却下/取消は無い
  expect(screen.queryByRole('button', { name: /却下|取消/ })).not.toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /^完了$/ }))
  const confirmBtn = await screen.findByRole('button', { name: '完了にする' })
  expect(mockApi).toHaveBeenCalledTimes(1) // GET のみ＝complete は未実行

  mockApi.mockResolvedValueOnce({ ok: true })
  mockApi.mockResolvedValueOnce({
    items: [],
    counts: { proposal: 0, handoff: 0, publish: 0, human_task: 0, total: 0 },
  })
  await userEvent.click(confirmBtn)

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/human-tasks/human%3A1/complete')
  })
  expect(mockedToast.success).toHaveBeenCalled()
})
