import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgePage } from '../KnowledgePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const insightNote = {
  path: 'insights/foo-1234abcd.md',
  name: 'foo-1234abcd.md',
  title: 'テストインサイト',
  type: 'insight',
  canonical: 'vault',
  tags: ['ai', 'growth'],
  subdir: 'insights',
  managed: true,
}

const outcomeNote = {
  path: 'outcomes/bar-5678efgh.md',
  name: 'bar-5678efgh.md',
  title: 'アウトカムノート',
  type: 'outcome',
  canonical: 'json',
  tags: [],
  subdir: 'outcomes',
  managed: true,
}

const notesResponse = {
  vault_dir: '/home/user/.pantheon/vault',
  exists: true,
  notes: [insightNote, outcomeNote],
}

const resolvedWikilink = {
  type: 'insight',
  target: 'another-insight',
  alias: '別のインサイト',
  node_id: 'insight:another-insight',
  resolved: true,
  resolved_path: 'insights/another-insight-abcd.md',
}

const unresolvedWikilink = {
  type: 'org',
  target: 'MyOrg',
  alias: 'MyOrg',
  node_id: 'org:MyOrg',
  resolved: false,
  resolved_path: '',
}

const backlink = {
  path: 'playbooks/linked-playbook.md',
  title: 'リンクプレイブック',
}

const insightDetail = {
  path: 'insights/foo-1234abcd.md',
  name: 'foo-1234abcd.md',
  title: 'テストインサイト',
  type: 'insight',
  canonical: 'vault',
  frontmatter: { created: '2026-01-01' },
  body: '# テストインサイト\n\nこれはテスト本文です。',
  tags: ['ai', 'growth'],
  wikilinks: [resolvedWikilink, unresolvedWikilink],
  backlinks: [backlink],
  synced_at: '2026-06-25T12:00:00Z',
  has_conflict: false,
}

const outcomeDetail = {
  path: 'outcomes/bar-5678efgh.md',
  name: 'bar-5678efgh.md',
  title: 'アウトカムノート',
  type: 'outcome',
  canonical: 'json',
  frontmatter: {},
  body: 'アウトカム本文。',
  tags: [],
  wikilinks: [],
  backlinks: [],
  synced_at: '2026-06-25T10:00:00Z',
  has_conflict: false,
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('KnowledgePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('renders Phase 1 read-only label', async () => {
    mockApi.mockResolvedValue(notesResponse)
    renderWithRouter(<KnowledgePage />)
    // Label should be visible immediately (not behind a loading gate)
    expect(await screen.findByText(/Phase 1 は読み取り専用/)).toBeInTheDocument()
  })

  it('renders notes grouped by subdir with counts', async () => {
    mockApi.mockResolvedValue(notesResponse)
    renderWithRouter(<KnowledgePage />)

    // Wait for list to appear
    expect(await screen.findByText('テストインサイト')).toBeInTheDocument()
    expect(screen.getByText('アウトカムノート')).toBeInTheDocument()

    // Groups with counts
    expect(screen.getByText('insights')).toBeInTheDocument()
    expect(screen.getByText('outcomes')).toBeInTheDocument()
    // Each group badge shows 1
    const badges = screen.getAllByText('1')
    expect(badges.length).toBeGreaterThanOrEqual(2)
  })

  it('selecting a note calls getVaultNote and renders title + body', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)       // listVaultNotes
      .mockResolvedValueOnce(insightDetail)       // getVaultNote

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    // Title appears in detail pane (may be multiple h1s due to markdown; just check text is present)
    expect(await screen.findAllByRole('heading', { level: 1, name: 'テストインサイト' })).not.toHaveLength(0)
    // Body markdown text renders
    expect(screen.getByText(/これはテスト本文です/)).toBeInTheDocument()

    // api called with correct path for the note detail
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/foo-1234abcd.md')
  })

  it('getVaultNote is called with the note path', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    // Wait for detail to load (body text appears)
    await screen.findByText(/これはテスト本文です/)

    expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/foo-1234abcd.md')
  })

  it('resolved wikilink renders as clickable chip and navigates', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)             // open insight
      .mockResolvedValueOnce({                           // navigate to resolved target
        ...insightDetail,
        path: 'insights/another-insight-abcd.md',
        title: '別のインサイト詳細',
      })

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    // Wait for detail to load
    await screen.findByText(/これはテスト本文です/)

    // The resolved wikilink should appear as a clickable button in the リンク section
    const wikilinkButtons = screen.getAllByRole('button', { name: '別のインサイト' })
    expect(wikilinkButtons.length).toBeGreaterThan(0)

    // Click the first one to navigate
    await user.click(wikilinkButtons[0])

    // Should have called getVaultNote with the resolved path
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/another-insight-abcd.md')
  })

  it('unresolved wikilink renders as muted non-clickable text', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    // Wait for detail to load
    await screen.findByText(/これはテスト本文です/)

    // Unresolved link (org:MyOrg) appears as a span, not a button
    const unresolvedChips = screen.getAllByText('MyOrg')
    expect(unresolvedChips.length).toBeGreaterThan(0)
    // Should be a span (not a button)
    const spanChip = unresolvedChips.find((el) => el.tagName === 'SPAN')
    expect(spanChip).toBeTruthy()
  })

  it('backlink renders and clicking loads the linked note', async () => {
    const linkedDetail = {
      ...insightDetail,
      path: 'playbooks/linked-playbook.md',
      title: 'リンクプレイブック詳細',
      type: 'playbook',
    }
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)
      .mockResolvedValueOnce(linkedDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    // Wait for detail to load
    await screen.findByText(/これはテスト本文です/)

    // Backlink chip should be present
    const backlinkBtn = screen.getByRole('button', { name: 'リンクプレイブック' })
    expect(backlinkBtn).toBeInTheDocument()

    // Click backlink
    await user.click(backlinkBtn)

    expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/playbooks/linked-playbook.md')
  })

  it('renders "読み取り専用ミラー" badge for canonical=json note', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(outcomeDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('アウトカムノート')
    await user.click(screen.getByRole('button', { name: 'アウトカムノート' }))

    expect(await screen.findByText('読み取り専用ミラー')).toBeInTheDocument()
  })

  it('renders empty state when notes list is empty', async () => {
    mockApi.mockResolvedValue({
      vault_dir: '/home/user/.pantheon/vault',
      exists: true,
      notes: [],
    })
    renderWithRouter(<KnowledgePage />)

    expect(await screen.findByText('まだ Vault がありません')).toBeInTheDocument()
    expect(screen.getByText(/pantheon vault export/)).toBeInTheDocument()
  })

  it('renders empty state when vault does not exist', async () => {
    mockApi.mockResolvedValue({
      vault_dir: '/home/user/.pantheon/vault',
      exists: false,
      notes: [],
    })
    renderWithRouter(<KnowledgePage />)

    expect(await screen.findByText('まだ Vault がありません')).toBeInTheDocument()
  })

  it('shows error state on load failure with retry button', async () => {
    mockApi.mockRejectedValue(new Error('vault fetch failed'))
    renderWithRouter(<KnowledgePage />)

    await waitFor(() => {
      expect(screen.getByText('Vault の読み込みに失敗しました')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    mockApi.mockReturnValue(new Promise(() => {}))
    renderWithRouter(<KnowledgePage />)
    expect(screen.getByText('Vault を読み込み中…')).toBeInTheDocument()
  })
})
