/**
 * App.tsx シェルのユニットテスト。
 *
 * AppShell（ツールバー）を中心に検証する。
 * ルート配下の各ページは mockApi が最低限のダミー値を返すことで、
 * 描画エラーを起こさない状態にする。
 *
 * 検証対象:
 *   C007 - ベルバッジが GET /api/notifications/unread-count の値を反映する
 *   C007 - ベルクリックでポップオーバーが開き GET /api/notifications?limit=8 を叩く
 *   C007 - 「すべて既読」が POST /api/notifications/read-all を叩く
 *   C025 - ↑/↓/Enter/Escape でドロップダウンを操作できる
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '@/App'
import { mockApi } from '@/test/mocks'
import { PlatformUpdatesProvider } from '@/hooks/usePlatformUpdates'

// PlatformUpdatesProvider がある環境でレンダリングする共通ヘルパー。
// App は内部で Routes を持つため MemoryRouter で包む。
function renderApp(initialPath = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <PlatformUpdatesProvider>
        <App />
      </PlatformUpdatesProvider>
    </MemoryRouter>,
  )
}

// AppShell が起動時に叩く最低限の API を全部スタブにする。
// ダッシュボードページが要求する API を含む。
function wireMinimalApi({
  unread = 0,
}: {
  unread?: number
} = {}) {
  const notifList = {
    items: [] as { id: string; level: string; message: string; org_name: string | null; read: boolean; route: string | null }[],
    unread,
  }

  mockApi.mockImplementation(async (method: string, path: string) => {
    // AppShell（環境バッジ）
    if (method === 'GET' && path === '/api/platform/status')
      return { environment: 'development', env_label: 'DEV', initialized: true, has_llm: true, group_health_score: 0, balance_score: 0, total_organizations: 0, active_organizations: 0, weakest_organization: null, strongest_organization: null, platform_home: '/tmp' }
    // C007: 未読数バッジ
    if (method === 'GET' && path === '/api/notifications/unread-count')
      return { unread }
    // C007: ポップオーバーの通知一覧（limit=8）
    if (method === 'GET' && path === '/api/notifications?limit=8')
      return notifList
    // ダッシュボードページが必要とする API
    if (method === 'GET' && path === '/api/settings')
      return { llm_provider: 'anthropic', llm_model: 'claude', settings_file: '/tmp', has_llm: true }
    if (method === 'GET' && path === '/api/organizations') return []
    if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
    if (method === 'GET' && path === '/api/tasks') return { tasks: [], stats: { total: 0, pending: 0, running: 0, done: 0, failed: 0 } }
    if (method === 'GET' && path === '/api/execution-history?limit=40') return []
    // 検索
    if (method === 'GET' && path.startsWith('/api/search'))
      return [
        { id: 'r1', type: 'organization', title: '検索結果A', subtitle: 'サブ', route: '/orgs', org_name: null, status: null },
        { id: 'r2', type: 'agent', title: '検索結果B', subtitle: 'サブ2', route: '/agents', org_name: null, status: null },
      ]
    // その他は空オブジェクトを返して静かにする
    return {}
  })
}

describe('App シェル（C007 ベル刷新）', () => {
  beforeEach(() => {
    mockApi.mockReset()
  })

  it('未読数バッジが /api/notifications/unread-count 由来の件数を表示する', async () => {
    wireMinimalApi({ unread: 5 })
    renderApp()

    // ベルの未読数バッジが「5」を表示するのを待つ
    expect(await screen.findByText('5')).toBeInTheDocument()
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/notifications/unread-count')
  })

  it('未読数が 0 のときバッジを表示しない', async () => {
    wireMinimalApi({ unread: 0 })
    renderApp()

    // 未読0ならベルのラベルは「通知を開く」（未読件数を含まない）＝バッジ非表示。
    // 全App描画では Dashboard 等が "0" を含むため、バッジ要素に限定して検証する。
    const bell = await screen.findByRole('button', { name: '通知を開く' })
    expect(bell.querySelector('.notification-count')).toBeNull()
  })

  it('ベルをクリックするとポップオーバーが開き GET /api/notifications?limit=8 を叩く', async () => {
    wireMinimalApi({ unread: 3 })
    const user = userEvent.setup()
    renderApp()

    // ベルボタンを探してクリック
    const bellBtn = await screen.findByRole('button', { name: /通知.*を開く/ })
    await user.click(bellBtn)

    // ポップオーバーが開くのを待つ
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('GET', '/api/notifications?limit=8'),
    )
  })

  it('ポップオーバーが空のとき「新しい通知はありません」と表示する', async () => {
    wireMinimalApi({ unread: 0 })
    const user = userEvent.setup()
    renderApp()

    await screen.findByText('DEV')
    const bellBtn = screen.getByRole('button', { name: /通知.*を開く/ })
    await user.click(bellBtn)

    expect(await screen.findByText('新しい通知はありません。')).toBeInTheDocument()
  })

  it('通知アイテムがあるとき「すべて既読」ボタンが現れ POST /api/notifications/read-all を叩く', async () => {
    // 未読アイテムを 1 件持つ通知リストを返すよう上書き
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/platform/status')
        return { environment: 'development', env_label: 'DEV', initialized: true, has_llm: true, group_health_score: 0, balance_score: 0, total_organizations: 0, active_organizations: 0, weakest_organization: null, strongest_organization: null, platform_home: '/tmp' }
      if (method === 'GET' && path === '/api/notifications/unread-count')
        return { unread: 1 }
      if (method === 'GET' && path === '/api/notifications?limit=8')
        return {
          items: [{ id: 'n1', level: 'info', message: 'テスト通知', org_name: null, read: false, route: null }],
          unread: 1,
        }
      if (method === 'POST' && path === '/api/notifications/read-all')
        return { ok: true, marked: 1, unread: 0 }
      if (method === 'GET' && path === '/api/settings') return { llm_provider: 'anthropic', llm_model: 'claude', settings_file: '/tmp', has_llm: true }
      if (method === 'GET' && path === '/api/organizations') return []
      if (method === 'GET' && path === '/api/daemon/status') return { running: false, pid: null, log_path: null }
      if (method === 'GET' && path === '/api/tasks') return { tasks: [], stats: { total: 0, pending: 0, running: 0, done: 0, failed: 0 } }
      if (method === 'GET' && path === '/api/execution-history?limit=40') return []
      return {}
    })

    const user = userEvent.setup()
    renderApp()

    await screen.findByText('DEV')
    const bellBtn = screen.getByRole('button', { name: /通知.*を開く/ })
    await user.click(bellBtn)

    // 「テスト通知」が表示される
    expect(await screen.findByText('テスト通知')).toBeInTheDocument()

    // 「すべて既読」ボタンをクリック
    const popover = screen.getByRole('dialog', { name: '通知' })
    const readAllBtn = within(popover).getByRole('button', { name: 'すべて既読' })
    await user.click(readAllBtn)

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/notifications/read-all'),
    )
  })

  it('Escape キーで通知ポップオーバーを閉じる', async () => {
    wireMinimalApi({ unread: 0 })
    const user = userEvent.setup()
    renderApp()

    await screen.findByText('DEV')
    const bellBtn = screen.getByRole('button', { name: /通知.*を開く/ })
    await user.click(bellBtn)

    expect(await screen.findByText('新しい通知はありません。')).toBeInTheDocument()

    // Escape で閉じる
    await user.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByText('新しい通知はありません。')).not.toBeInTheDocument(),
    )
  })
})

describe('App シェル（C025 検索 a11y）', () => {
  beforeEach(() => {
    mockApi.mockReset()
  })

  it('検索入力に role=combobox と aria-expanded が付いている', async () => {
    wireMinimalApi()
    renderApp()

    await screen.findByText('DEV')
    const input = screen.getByRole('combobox', { name: '全体検索' })
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-expanded', 'false')
  })

  it('2文字以上入力すると検索結果にアクセシブルな role=option が付く', async () => {
    wireMinimalApi()
    renderApp()

    await screen.findByText('DEV')
    const input = screen.getByRole('combobox', { name: '全体検索' })
    fireEvent.change(input, { target: { value: 'テスト' } })

    // API から結果が返るのを待つ
    expect(await screen.findByRole('option', { name: /検索結果A/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /検索結果B/ })).toBeInTheDocument()
  })

  it('↓キーで候補を選択状態にし Enter で遷移する', async () => {
    wireMinimalApi()
    const user = userEvent.setup()
    renderApp()

    await screen.findByText('DEV')
    const input = screen.getByRole('combobox', { name: '全体検索' })
    await user.type(input, 'テスト')

    // 結果が出るのを待つ
    await screen.findByRole('option', { name: /検索結果A/ })

    // ↓ で最初の候補をアクティブに
    await user.keyboard('{ArrowDown}')
    const optA = screen.getByRole('option', { name: /検索結果A/ })
    expect(optA).toHaveAttribute('aria-selected', 'true')

    // ↓ でさらに次へ
    await user.keyboard('{ArrowDown}')
    const optB = screen.getByRole('option', { name: /検索結果B/ })
    expect(optB).toHaveAttribute('aria-selected', 'true')

    // ↑ で戻る
    await user.keyboard('{ArrowUp}')
    expect(optA).toHaveAttribute('aria-selected', 'true')

    // Enter で遷移（SearchResults が消える）
    await user.keyboard('{Enter}')
    await waitFor(() =>
      expect(screen.queryByRole('option', { name: /検索結果A/ })).not.toBeInTheDocument(),
    )
  })

  it('Escape キーでドロップダウンを閉じる', async () => {
    wireMinimalApi()
    const user = userEvent.setup()
    renderApp()

    await screen.findByText('DEV')
    const input = screen.getByRole('combobox', { name: '全体検索' })
    await user.type(input, 'テスト')

    await screen.findByRole('option', { name: /検索結果A/ })

    await user.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
  })
})
