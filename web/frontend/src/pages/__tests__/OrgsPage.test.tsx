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
  agents: [
    { id: 'agent-1', name: 'Planner', capability_id: 'planner', skills: ['analysis'] },
  ],
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
      expect(screen.getByText('RepoCorp AI へようこそ')).toBeInTheDocument()
    })
  })

  it('renders the welcome state when no organizations exist', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('RepoCorp AI へようこそ')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'サンプル組織で始める' })).toBeInTheDocument()
  })

  it('shows an error toast when loading organizations fails', async () => {
    mockApi.mockRejectedValue(new Error('org load failed'))

    renderWithRouter(<OrgsPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('org load failed')
    })
  })

  it('creates a sample organization from the welcome state', async () => {
    let currentOrgs: typeof baseOrg[] = []
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return currentOrgs
      if (method === 'POST' && path === '/api/welcome') {
        currentOrgs = [baseOrg]
        return { created: ['acme-platform'] }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('RepoCorp AI へようこそ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'サンプル組織で始める' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('サンプル組織「acme-platform」を作成しました。')
    })
    expect(await screen.findByText('acme-platform')).toBeInTheDocument()
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

    expect(await screen.findByText('RepoCorp AI へようこそ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '組織を自分で作成' }))
    await user.type(screen.getByLabelText('名前'), 'beta-team')
    await user.type(screen.getByLabelText('目的'), 'Build a beta product')
    await user.type(screen.getByLabelText('対象リポジトリパス'), '/Users/test/repos/beta')
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

  it('renders score bars for health and autonomy', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    const orgListItem = await screen.findByRole('button', { name: 'acme-platform の詳細を開く' })
    expect(within(orgListItem).getByText('健康')).toBeInTheDocument()
    expect(within(orgListItem).getByText('自律')).toBeInTheDocument()
    expect(within(orgListItem).getByText('72')).toBeInTheDocument()
    expect(within(orgListItem).getByText('58')).toBeInTheDocument()
    expect(orgListItem.querySelectorAll('.score-bar-fill')).toHaveLength(2)
    expect(screen.getByText('コードレビュー通過率・改善実行率から算出。100が最高。')).toBeInTheDocument()
  })

  it('renders organizations as list items and opens the detail panel on click', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [baseOrg]
      if (method === 'GET' && path === '/api/organizations/acme-platform') return detailOrg
      if (method === 'GET' && path === '/api/organizations/acme-platform/proposals') return [detailProposal]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<OrgsPage />)

    const orgListItem = await screen.findByRole('button', { name: 'acme-platform の詳細を開く' })
    expect(orgListItem).toHaveClass('org-list-item')
    expect(within(orgListItem).getByAltText('acme-platform')).toBeInTheDocument()

    await user.click(orgListItem)

    expect(await screen.findByText('Planner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'アイコン変更' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'リセット' })).toBeInTheDocument()
    expect(screen.getByText('未対応の改善提案')).toBeInTheDocument()
    expect(screen.getByText('Split the dashboard widget')).toBeInTheDocument()
    expect(screen.getAllByText('/Users/test/repos/acme').length).toBeGreaterThan(0)
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

  it('shows a lock icon instead of a delete action for system organizations', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return [systemOrg]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrgsPage />)

    expect(await screen.findByText('meta-improvement')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'システム組織は削除できません' })).toBeDisabled()
    expect(screen.queryByLabelText('meta-improvement を削除')).not.toBeInTheDocument()
  })

  it('deletes an organization only after the two-step confirmation matches the name', async () => {
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

    const stepOneDialog = screen.getByRole('dialog', { name: '組織を削除' })
    expect(within(stepOneDialog).getByText(/この操作は取り消せません/)).toBeInTheDocument()
    await user.click(within(stepOneDialog).getByRole('button', { name: '次へ' }))

    const stepTwoDialog = screen.getByRole('dialog', { name: '組織を削除' })
    const deleteButton = within(stepTwoDialog).getByRole('button', { name: '削除する' })
    expect(deleteButton).toBeDisabled()

    const input = within(stepTwoDialog).getByRole('textbox')
    await user.type(input, 'wrong-name')
    expect(deleteButton).toBeDisabled()

    await user.clear(input)
    await user.type(input, 'acme-platform')
    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('組織を削除しました。')
    })
    expect(await screen.findByText('RepoCorp AI へようこそ')).toBeInTheDocument()
  })
})
