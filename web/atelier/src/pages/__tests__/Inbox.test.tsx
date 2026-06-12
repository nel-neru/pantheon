import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Inbox } from '../Inbox'
import type { InboxPayload } from '@/lib/types'

// ベースのフェッチモック: 空レスポンスで全エンドポイントを成功させる。
// 各テストで inbox ペイロードだけ上書きする。
function mockFetch(inboxPayload: InboxPayload) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/inbox')) {
      return { ok: true, json: async () => inboxPayload }
    }
    // 残りのエンドポイント（/api/organizations, /api/handoffs）は空配列を返す
    return { ok: true, json: async () => [] }
  }) as unknown as typeof fetch
}

const queuedItem = {
  kind: 'publish',
  id: 'job-1',
  org_name: 'ContentOrg',
  title: 'はじめての note 記事',
  category: 'note',
  priority: 'normal',
  platform: 'note',
  scheduled_at: null,
  status: 'queued' as const,
  route: 'note',
}

const handedOffItem = {
  kind: 'publish',
  id: 'job-2',
  org_name: 'ContentOrg',
  title: 'Twitter スレッドの確認',
  category: 'twitter',
  priority: 'normal',
  platform: 'twitter',
  scheduled_at: null,
  status: 'handed_off' as const,
  route: 'twitter',
}

describe('Inbox Publishing section', () => {
  beforeEach(() => {
    mockFetch({ items: [], counts: {} })
  })

  it('queued item shows 投稿 and 取消 buttons, not 公開を確認', async () => {
    mockFetch({ items: [queuedItem], counts: { publish: 1 } })
    render(<Inbox />)

    await waitFor(() => expect(screen.getByText('はじめての note 記事')).toBeInTheDocument())

    expect(screen.getByRole('button', { name: '投稿' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '公開を確認' })).not.toBeInTheDocument()
  })

  it('queued item shows 投稿待ち status tag', async () => {
    mockFetch({ items: [queuedItem], counts: { publish: 1 } })
    render(<Inbox />)

    await waitFor(() => expect(screen.getByText('投稿待ち')).toBeInTheDocument())
    expect(screen.queryByText('公開確認待ち')).not.toBeInTheDocument()
  })

  it('handed_off item shows ONLY 公開を確認 button (not 投稿 or 取消)', async () => {
    mockFetch({ items: [handedOffItem], counts: { publish: 1 } })
    render(<Inbox />)

    await waitFor(() => expect(screen.getByText('Twitter スレッドの確認')).toBeInTheDocument())

    expect(screen.getByRole('button', { name: '公開を確認' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '投稿' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '取消' })).not.toBeInTheDocument()
  })

  it('handed_off item shows 公開確認待ち status tag', async () => {
    mockFetch({ items: [handedOffItem], counts: { publish: 1 } })
    render(<Inbox />)

    await waitFor(() => expect(screen.getByText('公開確認待ち')).toBeInTheDocument())
    expect(screen.queryByText('投稿待ち')).not.toBeInTheDocument()
  })

  it('公開を確認 click POSTs /api/publish-jobs/{id}/confirm', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [handedOffItem], counts: { publish: 1 } }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch
    globalThis.fetch = fetchMock

    render(<Inbox />)
    await waitFor(() => expect(screen.getByText('Twitter スレッドの確認')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '公開を確認' }))

    // /api/publish-jobs/job-2/confirm に POST が飛んだことを確認
    await waitFor(() => {
      const calls = (fetchMock as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit][]
      const confirmCall = calls.find(
        ([url, opts]) =>
          String(url).includes('/api/publish-jobs/job-2/confirm') && opts?.method === 'POST',
      )
      expect(confirmCall).toBeDefined()
    })
  })

  it('投稿 click POSTs /api/publish-jobs/{id}/run', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [queuedItem], counts: { publish: 1 } }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch
    globalThis.fetch = fetchMock

    render(<Inbox />)
    await waitFor(() => expect(screen.getByText('はじめての note 記事')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '投稿' }))

    // /api/publish-jobs/job-1/run に POST が飛んだことを確認
    await waitFor(() => {
      const calls = (fetchMock as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit][]
      const runCall = calls.find(
        ([url, opts]) =>
          String(url).includes('/api/publish-jobs/job-1/run') && opts?.method === 'POST',
      )
      expect(runCall).toBeDefined()
    })
  })

  it('取消の in-flight 中は 投稿 も disabled（同一ジョブへの並行 run/delete を防ぐ）', async () => {
    const user = userEvent.setup()
    // DELETE を未解決のまま保留し、in-flight 状態を観察できるようにする
    let resolveDelete: (() => void) | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/publish-jobs/') && init?.method === 'DELETE') {
        await new Promise<void>((resolve) => {
          resolveDelete = resolve
        })
        return { ok: true, json: async () => ({ status: 'deleted' }) }
      }
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [queuedItem], counts: { publish: 1 } }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch
    globalThis.fetch = fetchMock

    render(<Inbox />)
    await waitFor(() => expect(screen.getByText('はじめての note 記事')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '取消' }))

    await waitFor(() => expect(screen.getByRole('button', { name: '投稿' })).toBeDisabled())
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()

    resolveDelete?.()
  })

  it('Publishing stat shows the sub-label and both items', async () => {
    mockFetch({ items: [queuedItem, handedOffItem], counts: { publish: 2 } })
    render(<Inbox />)

    // Publishing stat sub-label is unique on the page
    expect(screen.getByText('投稿・公開確認待ち')).toBeInTheDocument()

    // Both items eventually render
    await waitFor(() => expect(screen.getByText('はじめての note 記事')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Twitter スレッドの確認')).toBeInTheDocument())
  })

  it('shows empty state when no publish items', async () => {
    mockFetch({ items: [], counts: {} })
    render(<Inbox />)

    await waitFor(() =>
      expect(screen.getByText('投稿・公開確認待ちのジョブはありません')).toBeInTheDocument(),
    )
  })
})
