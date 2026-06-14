import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { OrgsPage } from '../OrgsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
  info: ReturnType<typeof vi.fn>
}

const baseOrg = {
  id: 'org-1',
  name: 'acme-platform',
  purpose: 'Improve the platform',
  health_score: 72,
  autonomy_score: 58,
  total_agents: 4,
  pending_proposals: 2,
  target_repo_path: '/Users/test/repos/acme',
  status: 'active',
  last_active: '2025-01-01T10:00:00.000Z',
  is_system: false,
}

const detailOrg = {
  ...baseOrg,
  icon_data: 'data:image/png;base64,ZmFrZQ==',
  initial_kpis: ['有料記事の売上'],
  agents: [
    { id: 'agent-1', name: 'Planner', capability_id: 'planner', skills: ['analysis'] },
  ],
  divisions: [],
}

const detailProposal = {
  id: 'proposal-1',
  title: 'Split the dashboard widget',
  description: 'Reduce complexity',
  priority: 'high',
  status: 'pending',
  file_path: 'src/pages/DashboardPage.tsx',
}

const systemOrg = {
  ...baseOrg,
  id: 'org-system',
  name: 'meta-improvement',
  is_system: true,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('OrgsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while organizations are loading', async () => {
    const request = deferred<typeof baseOrg[]>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return request.promise
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    expect(screen.getByText('組織を読み込み中…')).toBeInTheDocument()

    request.resolve([])
    await waitFor(() => {
      expect(screen.getByText('Pantheon へようこそ')).toBeInTheDocument()
    })
  })

  it('renders the welcome state when no organizations exist', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('Pantheon へようこそ')).toBeInTheDocument()
    // 実データのみ: サンプル組織生成ボタンは廃止。実 repo 指定の「組織を作成」のみ。
    expect(screen.getByRole('button', { name: '組織を作成' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'サンプル組織で始める' })).not.toBeInTheDocument()
  })

  it('shows an error toast when loading organizations fails', async () => {
    mockApi.mockRejectedValue(new Error('org load failed'))

    renderWithRouter(<OrgsPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('org load failed')
    })
  })

  it('creates a custom organization from the modal form', async () => {
    let currentOrgs: typeof baseOrg[] = []
    mockApi.mockImplementation(async (method, path, body) => {
      if (method === 'GET' && path === '/api/organizations') return currentOrgs
      if (method === 'POST' && path === '/api/organizations') {
        currentOrgs = [
          {
            ...baseOrg,
            name: (body as { name: string }).name,
            purpose: (body as { purpose: string }).purpose,
            target_repo_path: (body as { target_repo_path: string }).target_repo_path,
          },
        ]
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('Pantheon へようこそ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '組織を作成' }))
    await user.type(screen.getByLabelText('名前'), 'beta-team')
    await user.type(screen.getByLabelText('目的'), 'Build a beta product')
    await user.type(
      screen.getByLabelText('対象ワークスペース（git リポジトリ）の絶対パス'),
      '/Users/test/repos/beta',
    )
    await user.click(screen.getByRole('button', { name: '作成' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('組織を作成しました。')
    })
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/organizations', {
      name: 'beta-team',
      purpose: 'Build a beta product',
      target_repo_path: '/Users/test/repos/beta',
    })
    expect(await screen.findByText('beta-team')).toBeInTheDocument()
  })

  it('cancel button on create modal resets the form', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('Pantheon へようこそ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '組織を作成' }))
    await user.type(screen.getByLabelText('名前'), 'partial-org')
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    // dialog should close
    await waitFor(() => {
      expect(screen.queryByLabelText('名前')).not.toBeInTheDocument()
    })

    // re-open: form should be empty
    await user.click(screen.getByRole('button', { name: '組織を作成' }))
    expect(screen.getByLabelText('名前')).toHaveValue('')
  })

  it('renders score bars for health and autonomy using ScoreBar component', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    await screen.findByText('acme-platform')
    // ScoreBar renders with role=meter and aria-label
    const healthBar = screen.getByRole('meter', { name: '健康スコア' })
    expect(healthBar).toBeInTheDocument()
    expect(healthBar).toHaveAttribute('aria-valuenow', '72')
    const autonomyBar = screen.getByRole('meter', { name: '自律スコア' })
    expect(autonomyBar).toBeInTheDocument()
    expect(autonomyBar).toHaveAttribute('aria-valuenow', '58')
    // score-bar-fill is a child of the track inside the meter
    expect(healthBar.querySelectorAll('.score-bar-fill')).toHaveLength(1)
  })

  it('opens the detail panel via the chevron button and renders org details', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return [detailProposal]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await screen.findByText('acme-platform')
    // Detail is now opened via the Chevron button, not the whole card
    const chevronBtn = screen.getByRole('button', { name: 'acme-platform の詳細を開く' })
    await user.click(chevronBtn)

    expect(await screen.findByText('Planner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'アイコン変更' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'リセット' })).toBeInTheDocument()
    expect(screen.getByText('未対応の改善提案')).toBeInTheDocument()
    expect(screen.getByText('Split the dashboard widget')).toBeInTheDocument()
    expect(screen.getAllByText('/Users/test/repos/acme').length).toBeGreaterThan(0)
    // TPL-SEED: 初期KPI が詳細に表示される
    expect(screen.getByText('初期KPI')).toBeInTheDocument()
    expect(screen.getByText('有料記事の売上')).toBeInTheDocument()
  })

  it('detail panel is a Radix Dialog and closes with Esc key', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))
    expect(await screen.findByText('Planner')).toBeInTheDocument()

    // Dialog should have role=dialog
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()

    // Close via Escape
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByText('Planner')).not.toBeInTheDocument()
    })
  })

  it('status badge uses statusLabel mapping (active → 稼働中)', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    await screen.findByText('acme-platform')
    // status='active' → statusLabel → '稼働中'
    expect(screen.getByText('稼働中')).toBeInTheDocument()
  })

  it('shows a specific not-found message when loading details returns 404', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') {
        throw new Error("Organization 'acme-platform' が見つかりません")
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('組織「acme-platform」は見つかりません。一覧を更新して再度お試しください。')
    })
  })

  it('shows a specific network message when loading details fails to fetch', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') {
        throw new Error('Failed to fetch')
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('組織詳細の取得中にネットワークエラーが発生しました。接続を確認して再試行してください。')
    })
  })

  it('edits an existing organization', async () => {
    let currentOrgs = [baseOrg]
    mockApi.mockImplementation(async (method, path, body) => {
      if (method === 'GET' && path === '/api/organizations') return currentOrgs
      if (method === 'PUT' && path === '/api/organizations/acme-platform') {
        currentOrgs = currentOrgs.map((org) => ({
          ...org,
          purpose: (body as { purpose: string }).purpose,
          target_repo_path: (body as { target_repo_path: string }).target_repo_path,
        }))
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('acme-platform')).toBeInTheDocument()
    await user.click(screen.getByLabelText('acme-platform を編集'))

    const purposeInput = screen.getByLabelText('目的')
    await user.clear(purposeInput)
    await user.type(purposeInput, 'Improve the org workflows')
    const repoInput = screen.getByLabelText('対象リポジトリパス')
    await user.clear(repoInput)
    await user.type(repoInput, '/Users/test/repos/acme-updated')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('組織を更新しました。')
    })
    expect(await screen.findByText('Improve the org workflows')).toBeInTheDocument()
  })

  it('migrates a repo org to workspace mode via ConfirmDialog', async () => {
    let currentDetail = { ...detailOrg, management_mode: 'repo' as string }
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return currentDetail
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return []
      if (
        method === 'POST' &&
        path === '/api/organizations/acme-platform/migrate-to-workspace'
      ) {
        currentDetail = { ...currentDetail, management_mode: 'workspace' }
        return { already_workspace: false }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))
    // The migrate button now opens a ConfirmDialog first
    await user.click(await screen.findByRole('button', { name: 'workspace へ移行' }))

    // Confirm dialog should appear
    const confirmDialog = await screen.findByRole('dialog', { name: 'workspace へ移行' })
    expect(within(confirmDialog).getByText(/元に戻すことはできません/)).toBeInTheDocument()

    // Click "移行する" to confirm
    await user.click(within(confirmDialog).getByRole('button', { name: '移行する' }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        'POST',
        '/api/organizations/acme-platform/migrate-to-workspace'
      )
    })
    expect(await screen.findByText('workspace（git 不要）')).toBeInTheDocument()
  })

  it('shows a lock icon for system organizations without a delete button', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [systemOrg]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('meta-improvement')).toBeInTheDocument()
    // System org: no delete button at all
    expect(screen.queryByLabelText('meta-improvement を削除')).not.toBeInTheDocument()
    // No disabled delete button (inline style anti-pattern removed)
    expect(screen.queryByRole('button', { name: 'システム組織は削除できません' })).not.toBeInTheDocument()
  })

  it('deletes an organization via ConfirmDialog with name-match confirmation', async () => {
    let currentOrgs = [baseOrg]
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return currentOrgs
      if (method === 'DELETE' && path === '/api/organizations/acme-platform') {
        currentOrgs = []
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('acme-platform')).toBeInTheDocument()
    await user.click(screen.getByLabelText('acme-platform を削除'))

    // ConfirmDialog opens (Radix Dialog)
    const dialog = await screen.findByRole('dialog', { name: '組織を削除' })
    expect(within(dialog).getByText(/この操作は取り消せません/)).toBeInTheDocument()

    // The confirm button should be disabled until the org name is typed
    const deleteButton = within(dialog).getByRole('button', { name: '削除する' })
    expect(deleteButton).toBeDisabled()

    const input = within(dialog).getByRole('textbox', { name: '確認文字列' })
    await user.type(input, 'wrong-name')
    expect(deleteButton).toBeDisabled()

    await user.clear(input)
    await user.type(input, 'acme-platform')
    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('組織を削除しました。')
    })
    expect(await screen.findByText('Pantheon へようこそ')).toBeInTheDocument()
  })

  it('icon reset requires ConfirmDialog confirmation', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return []
      if (method === 'DELETE' && path === '/api/organizations/acme-platform/icon') {
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))
    await user.click(await screen.findByRole('button', { name: 'リセット' }))

    // ConfirmDialog opens
    const dialog = await screen.findByRole('dialog', { name: 'アイコンをリセット' })
    expect(within(dialog).getByText(/設定済みのアイコンを削除します/)).toBeInTheDocument()

    // API should NOT have been called yet
    expect(mockApi).not.toHaveBeenCalledWith('DELETE', '/api/organizations/acme-platform/icon')

    // Confirm
    await user.click(within(dialog).getByRole('button', { name: 'リセット' }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('DELETE', '/api/organizations/acme-platform/icon')
    })
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('アイコンをリセットしました。')
    })
  })

  it('proposal list shows link to improvements page', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return [detailProposal]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))
    expect(await screen.findByText('Split the dashboard widget')).toBeInTheDocument()

    // Priority label should be Japanese from priorityLabel
    expect(screen.getByText('高')).toBeInTheDocument()

    // Link to improvements inbox
    const link = screen.getByRole('link', { name: '承認インボックスで開く →' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('/improvements'))
  })

  it('proposal error and empty state show distinct messages', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') {
        throw new Error('proposals fetch failed')
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    await user.click(await screen.findByRole('button', { name: 'acme-platform の詳細を開く' }))

    await waitFor(() => {
      expect(screen.getByText('proposals fetch failed')).toBeInTheDocument()
    })
    // Should NOT show the "no proposals" empty text when there's an error
    expect(screen.queryByText('未対応の提案はありません。')).not.toBeInTheDocument()
  })
})
