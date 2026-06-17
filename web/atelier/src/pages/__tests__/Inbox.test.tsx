import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
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

describe('Inbox Proposals section error handling', () => {
  it('shows an error note (not a perpetual loading spinner) when /api/organizations fails', async () => {
    // /api/organizations だけ失敗させる。これが失敗すると orgsSig が永久に null になり、
    // 以前は Proposals セクションが「提案を集約」で無限ローディングし、エラーも出なかった。
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/organizations')) {
        return {
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          json: async () => ({ detail: '組織一覧の取得に失敗しました' }),
        }
      }
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [], counts: {} }) }
      }
      // /api/handoffs などは成功（空）
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch

    render(<Inbox />)

    // ErrorNote が出る（"接続エラー" は単一テキストノードで確実に拾える）
    await waitFor(() => expect(screen.getByText('接続エラー')).toBeInTheDocument())
    // バックエンドのエラーメッセージも面に出る
    expect(
      screen.getByText(
        (_, el) => el?.tagName === 'P' && Boolean(el.textContent?.includes('組織一覧の取得に失敗しました')),
      ),
    ).toBeInTheDocument()
    // 無限ローディングの「提案を集約」は出ない（回帰の核心）
    expect(screen.queryByText(/提案を集約/)).not.toBeInTheDocument()
    // 提案ゼロの誤誘導な空状態も出さない（エラーを空と取り違えない）
    expect(screen.queryByText('承認待ちの提案はありません')).not.toBeInTheDocument()
  })

  it('still shows the empty state (not an error) when /api/organizations succeeds with no pending proposals', async () => {
    // 健全系の対照: orgs 成功＝エラーを出さず、空状態に落ち着く（loadingProps が解ける）。
    mockFetch({ items: [], counts: {} })
    render(<Inbox />)

    await waitFor(() =>
      expect(screen.getByText('承認待ちの提案はありません')).toBeInTheDocument(),
    )
    expect(screen.queryByText('接続エラー')).not.toBeInTheDocument()
    expect(screen.queryByText(/提案を集約/)).not.toBeInTheDocument()
  })
})

// 最小限の OrgSummary を組み立てる（コンポーネントが使うのは name / pending_proposals のみ）。
function orgSummary(name: string, pending: number) {
  return {
    id: name,
    name,
    purpose: '',
    target_repo_path: null,
    status: 'active',
    health_score: 0,
    autonomy_score: 0,
    improvement_velocity: 0,
    total_agents: 0,
    pending_proposals: pending,
    last_active: '2026-06-17T00:00:00Z',
    is_system: false,
    icon_data: null,
  }
}

describe('Inbox Proposals section partial-failure observability', () => {
  it('一部の組織だけ提案フェッチが失敗したら、取得できた提案は出しつつ部分失敗を開示する', async () => {
    // OrgA は提案1件を返し、OrgB は 500。握り潰すと OrgB の提案が黙って消え、
    // 承認待ち件数が実際より少なく表示される（silent metric distortion）。
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      // per-org 提案エンドポイントを /api/organizations 判定より先に評価する。
      if (url.includes('/proposals')) {
        if (url.includes('/OrgB/')) {
          return {
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
            json: async () => ({ detail: 'OrgB proposals failed' }),
          }
        }
        return { ok: true, json: async () => [{ proposal_id: 'pA1', title: 'OrgA の改善提案' }] }
      }
      if (url.includes('/api/organizations')) {
        return { ok: true, json: async () => [orgSummary('OrgA', 1), orgSummary('OrgB', 1)] }
      }
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [], counts: {} }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch

    render(<Inbox />)

    // 取得できた OrgA の提案は表示される
    await waitFor(() => expect(screen.getByText('OrgA の改善提案')).toBeInTheDocument())
    // 部分失敗が面に出る（失敗 org 名を含む）
    expect(
      screen.getByText(
        (_, el) =>
          el?.tagName === 'P' &&
          Boolean(el.textContent?.includes('提案を取得できませんでした')) &&
          Boolean(el.textContent?.includes('OrgB')),
      ),
    ).toBeInTheDocument()
    // 提案が1件は出ているので空状態は出ない
    expect(screen.queryByText('承認待ちの提案はありません')).not.toBeInTheDocument()
  })

  it('全組織で提案フェッチが失敗しても「すべて捌けています」を捏造せず、エラーを開示する', async () => {
    // 全 org 失敗 → proposals は空。だが「空＝完了」ではないので EmptyState を出してはならない
    // （error を done に偽装しない）。代わりに部分失敗の開示を出す。
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/proposals')) {
        return {
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          json: async () => ({ detail: 'proposals failed' }),
        }
      }
      if (url.includes('/api/organizations')) {
        return { ok: true, json: async () => [orgSummary('OrgA', 1), orgSummary('OrgB', 1)] }
      }
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [], counts: {} }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch

    render(<Inbox />)

    // 部分失敗の開示が出る
    await waitFor(() =>
      expect(
        screen.getByText(
          (_, el) =>
            el?.tagName === 'P' && Boolean(el.textContent?.includes('提案を取得できませんでした')),
        ),
      ).toBeInTheDocument(),
    )
    // 誤誘導の「承認待ちの提案はありません（すべて捌けています）」を出さない（回帰の核心）
    expect(screen.queryByText('承認待ちの提案はありません')).not.toBeInTheDocument()
    // 無限ローディングにも陥らない
    expect(screen.queryByText(/提案を集約/)).not.toBeInTheDocument()
  })

  it('一度失敗した組織が次の poll で回復したら、部分失敗の開示は消える（スティッキー誤警告を防ぐ）', async () => {
    // orgsSig 依存のままだと pending_proposals 不変＝effect 再発火せず、回復後も注記が
    // 残り続ける。orgs.data 依存（poll 毎再評価）で failedOrgs を作り直すことを固定する。
    vi.useFakeTimers()
    try {
      let orgBCalls = 0
      globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/proposals')) {
          if (url.includes('/OrgB/')) {
            orgBCalls += 1
            if (orgBCalls === 1) {
              return {
                ok: false,
                status: 500,
                statusText: 'Internal Server Error',
                json: async () => ({ detail: 'transient' }),
              }
            }
          }
          return { ok: true, json: async () => [{ proposal_id: 'pB1', title: 'OrgB の改善提案' }] }
        }
        if (url.includes('/api/organizations')) {
          return { ok: true, json: async () => [orgSummary('OrgB', 1)] }
        }
        if (url.includes('/api/inbox')) {
          return { ok: true, json: async () => ({ items: [], counts: {} }) }
        }
        return { ok: true, json: async () => [] }
      }) as unknown as typeof fetch

      render(<Inbox />)
      // 初回マウントのフェッチ連鎖（orgs→per-org proposals）を flush
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })
      // 初回は OrgB 失敗 → 部分失敗の開示が出る
      expect(
        screen.getByText(
          (_, el) =>
            el?.tagName === 'P' && Boolean(el.textContent?.includes('提案を取得できませんでした')),
        ),
      ).toBeInTheDocument()

      // 次の orgs poll（45s）で OrgB が回復 → failedOrgs が作り直され注記が消える
      await act(async () => {
        await vi.advanceTimersByTimeAsync(45000)
      })
      expect(screen.queryByText(/提案を取得できませんでした/)).not.toBeInTheDocument()
      expect(screen.getByText('OrgB の改善提案')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('全組織の提案フェッチが成功すれば部分失敗の開示は出ない（健全系の対照）', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/proposals')) {
        return { ok: true, json: async () => [{ proposal_id: 'pA1', title: 'OrgA の改善提案' }] }
      }
      if (url.includes('/api/organizations')) {
        return { ok: true, json: async () => [orgSummary('OrgA', 1)] }
      }
      if (url.includes('/api/inbox')) {
        return { ok: true, json: async () => ({ items: [], counts: {} }) }
      }
      return { ok: true, json: async () => [] }
    }) as unknown as typeof fetch

    render(<Inbox />)

    await waitFor(() => expect(screen.getByText('OrgA の改善提案')).toBeInTheDocument())
    expect(screen.queryByText(/提案を取得できませんでした/)).not.toBeInTheDocument()
  })
})
