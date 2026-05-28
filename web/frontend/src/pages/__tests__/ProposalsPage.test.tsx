import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ProposalsPage } from '../ProposalsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const organizations = [{ name: 'alpha' }]

const pendingProposal = {
  id: 'proposal-1',
  title: 'Add tests',
  description: 'Increase coverage for the dashboard page.',
  priority: 'high',
  category: 'quality',
  file_path: 'src/pages/DashboardPage.tsx',
  status: 'pending',
}

const proposedProposal = {
  id: 'proposal-2',
  title: 'Review auth boundaries',
  description: 'Inspect the auth layer for hidden coupling.',
  priority: 'medium',
  category: 'architecture',
  file_path: 'src/pages/AuthPage.tsx',
  status: 'proposed',
}

const inProgressProposal = {
  id: 'proposal-3',
  title: 'Refactor org state',
  description: 'Split large state handlers into a hook.',
  priority: 'medium',
  category: 'architecture',
  file_path: 'src/pages/OrgsPage.tsx',
  status: 'in_progress',
}

const doneProposal = {
  id: 'proposal-4',
  title: 'Finalize caching layer',
  description: 'Persist the cache keys after rollout.',
  priority: 'low',
  category: 'performance',
  file_path: 'src/pages/CachePage.tsx',
  status: 'done',
}

const architecturePendingProposal = {
  id: 'proposal-5',
  title: 'Split dashboard widgets',
  description: 'Break the dashboard widgets into smaller components.',
  priority: 'medium',
  category: 'architecture',
  file_path: 'src/pages/DashboardPage.tsx',
  status: 'pending',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('ProposalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while proposals are loading', async () => {
    const request = deferred<typeof organizations>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return request.promise
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') return [pendingProposal]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    expect(screen.getByText('提案を読み込み中…')).toBeInTheDocument()

    request.resolve(organizations)
    await waitFor(() => {
      expect(screen.getByText('Add tests')).toBeInTheDocument()
    })
  })

  it('renders an empty state when no organizations exist', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<ProposalsPage />)

    expect(await screen.findByText('改善提案がありません')).toBeInTheDocument()
  })

  it('shows an error toast when proposals fail to load', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') {
        throw new Error('proposal load failed')
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('proposal load failed')
    })
  })

  it('treats proposed and in-progress proposals as active in the pending filter', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') {
        return [pendingProposal, proposedProposal, inProgressProposal, doneProposal]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    expect(await screen.findByText('Add tests')).toBeInTheDocument()
    expect(screen.getByText('Review auth boundaries')).toBeInTheDocument()
    expect(screen.getByText('Refactor org state')).toBeInTheDocument()
    expect(screen.queryByText('Finalize caching layer')).not.toBeInTheDocument()

    const [, statusFilter] = screen.getAllByRole('combobox')
    await user.selectOptions(statusFilter, 'in_progress')

    expect(await screen.findByText('Refactor org state')).toBeInTheDocument()
    expect(screen.queryByText('Add tests')).not.toBeInTheDocument()
    expect(screen.queryByText('Review auth boundaries')).not.toBeInTheDocument()

    await user.selectOptions(statusFilter, 'done')

    expect(await screen.findByText('Finalize caching layer')).toBeInTheDocument()
    expect(screen.queryByText('Refactor org state')).not.toBeInTheDocument()
  })

  it('renders a category filter and filters proposals by category', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') {
        return [pendingProposal, architecturePendingProposal]
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    expect(await screen.findByText('Add tests')).toBeInTheDocument()
    expect(screen.getByText('Split dashboard widgets')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '全カテゴリ' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'architecture' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'quality' })).toBeInTheDocument()

    const [, , categoryFilter] = screen.getAllByRole('combobox')
    await user.selectOptions(categoryFilter, 'architecture')

    expect(await screen.findByText('Split dashboard widgets')).toBeInTheDocument()
    expect(screen.queryByText('Add tests')).not.toBeInTheDocument()
  })

  it('approves a proposal', async () => {
    let currentProposals = [pendingProposal]
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') return currentProposals
      if (method === 'POST' && path === '/api/proposals/alpha/proposal-1/approve') {
        currentProposals = [{ ...pendingProposal, status: 'approved' }]
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    const card = await screen.findByText('Add tests')
    await user.click(within(card.closest('.proposal-card') as HTMLElement).getByRole('button', { name: '承認' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('提案を承認しました。')
    })
    expect(screen.getByText('承認済み')).toBeInTheDocument()
  })

  it('rejects a proposal', async () => {
    let currentProposals = [pendingProposal]
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/organizations') return organizations
      if (method === 'GET' && path === '/api/organizations/alpha/proposals') return currentProposals
      if (method === 'POST' && path === '/api/proposals/alpha/proposal-1/reject') {
        currentProposals = [{ ...pendingProposal, status: 'rejected' }]
        return { ok: true }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<ProposalsPage />, ['/proposals?org=alpha'])

    const card = await screen.findByText('Add tests')
    await user.click(within(card.closest('.proposal-card') as HTMLElement).getByRole('button', { name: '却下' }))

    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('提案を却下しました。')
    })
    expect(screen.getByText('却下済み')).toBeInTheDocument()
  })
})
