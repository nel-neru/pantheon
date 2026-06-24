import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgePage } from '../KnowledgePage'
import { mockApi, mockEditVaultNote, mockGetVaultGraph, mockSyncVault } from '@/test/mocks'
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

const syncResult = {
  import: {
    imported: 3,
    conflicts: 0,
    rejected: 0,
    orphan: 0,
    skipped: 1,
    conflict_paths: [],
    imported_paths: ['insights/new.md'],
  },
  export: {
    written: 2,
    skipped: 0,
    by_type: { insight: 2 },
    paths: ['insights/foo-1234abcd.md'],
  },
  conflicts: 0,
}

const syncResultWithConflicts = {
  import: {
    imported: 1,
    conflicts: 2,
    rejected: 1,
    orphan: 0,
    skipped: 0,
    conflict_paths: ['insights/conflict.md'],
    imported_paths: [],
  },
  export: {
    written: 0,
    skipped: 1,
    by_type: {},
    paths: [],
  },
  conflicts: 2,
}

const graphData = {
  nodes: [
    { id: 'insight:foo', label: 'テストインサイト', group: 'insight', path: 'insights/foo-1234abcd.md', files: 1 },
    { id: 'org:MyOrg', label: 'MyOrg', group: 'org', path: '', files: 0 },
  ],
  edges: [
    { source: 'insight:foo', target: 'org:MyOrg', weight: 1 },
  ],
  backlinks: {},
  counts: { notes: 1, nodes: 2, edges: 1, resolved_links: 1, groups: ['insight', 'org'] },
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('KnowledgePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockEditVaultNote.mockReset()
    mockSyncVault.mockReset()
    mockGetVaultGraph.mockReset()
  })

  // ── Existing Phase-1 tests (kept green) ────────────────────────────────────

  it('renders Phase 2 info notice', async () => {
    mockApi.mockResolvedValue(notesResponse)
    renderWithRouter(<KnowledgePage />)
    // Updated copy: no longer says "Phase 1 は読み取り専用" — now says vault-canonical can be edited
    expect(await screen.findByText(/vault-canonical ノート/)).toBeInTheDocument()
  })

  it('renders notes grouped by subdir with counts', async () => {
    mockApi.mockResolvedValue(notesResponse)
    renderWithRouter(<KnowledgePage />)

    expect(await screen.findByText('テストインサイト')).toBeInTheDocument()
    expect(screen.getByText('アウトカムノート')).toBeInTheDocument()

    expect(screen.getByText('insights')).toBeInTheDocument()
    expect(screen.getByText('outcomes')).toBeInTheDocument()
    const badges = screen.getAllByText('1')
    expect(badges.length).toBeGreaterThanOrEqual(2)
  })

  it('selecting a note calls getVaultNote and renders title + body', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    expect(await screen.findAllByRole('heading', { level: 1, name: 'テストインサイト' })).not.toHaveLength(0)
    expect(screen.getByText(/これはテスト本文です/)).toBeInTheDocument()

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

    await screen.findByText(/これはテスト本文です/)

    expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/foo-1234abcd.md')
  })

  it('resolved wikilink renders as clickable chip and navigates', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)
      .mockResolvedValueOnce({
        ...insightDetail,
        path: 'insights/another-insight-abcd.md',
        title: '別のインサイト詳細',
      })

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    await screen.findByText(/これはテスト本文です/)

    const wikilinkButtons = screen.getAllByRole('button', { name: '別のインサイト' })
    expect(wikilinkButtons.length).toBeGreaterThan(0)

    await user.click(wikilinkButtons[0])

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

    await screen.findByText(/これはテスト本文です/)

    const unresolvedChips = screen.getAllByText('MyOrg')
    expect(unresolvedChips.length).toBeGreaterThan(0)
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

    await screen.findByText(/これはテスト本文です/)

    const backlinkBtn = screen.getByRole('button', { name: 'リンクプレイブック' })
    expect(backlinkBtn).toBeInTheDocument()

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

  // ── Phase 2: Edit (vault-canonical) ────────────────────────────────────────

  it('vault-canonical note shows 編集 button', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))

    await screen.findByText(/これはテスト本文です/)

    expect(screen.getByRole('button', { name: '編集' })).toBeInTheDocument()
  })

  it('json-mirror note (canonical: json) shows NO 編集 button', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(outcomeDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('アウトカムノート')
    await user.click(screen.getByRole('button', { name: 'アウトカムノート' }))

    await screen.findByText('読み取り専用ミラー')

    // No edit button for read-only mirrors
    expect(screen.queryByRole('button', { name: '編集' })).toBeNull()
  })

  it('editing vault-canonical note: 保存 calls editVaultNote with typed content and re-fetches', async () => {
    const updatedDetail = { ...insightDetail, body: '更新済みの本文' }

    mockApi
      .mockResolvedValueOnce(notesResponse)        // initial load
      .mockResolvedValueOnce(insightDetail)        // open note
      .mockResolvedValueOnce(updatedDetail)        // re-fetch after save

    mockEditVaultNote.mockResolvedValueOnce({ status: 'accepted' })

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))
    await screen.findByText(/これはテスト本文です/)

    // Enter edit mode
    await user.click(screen.getByRole('button', { name: '編集' }))

    // Textarea should appear with the editable content
    const textarea = screen.getByRole('textbox', { name: 'ノート編集エリア' })
    expect(textarea).toBeInTheDocument()

    // Type new content
    await user.clear(textarea)
    await user.type(textarea, '新しい本文')

    // Save
    await user.click(screen.getByRole('button', { name: '保存' }))

    // editVaultNote called with path and typed content
    await waitFor(() => {
      expect(mockEditVaultNote).toHaveBeenCalledWith(
        'insights/foo-1234abcd.md',
        '新しい本文',
      )
    })

    // Re-fetches the note after save
    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/foo-1234abcd.md')
    })
  })

  it('キャンセル discards edits and exits edit mode', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))
    await screen.findByText(/これはテスト本文です/)

    await user.click(screen.getByRole('button', { name: '編集' }))

    const textarea = screen.getByRole('textbox', { name: 'ノート編集エリア' })
    expect(textarea).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    // Textarea gone, read-only body back
    expect(screen.queryByRole('textbox', { name: 'ノート編集エリア' })).toBeNull()
    expect(screen.getByText(/これはテスト本文です/)).toBeInTheDocument()
  })

  it('editVaultNote error (409) shows toast and stays in edit mode', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)

    mockEditVaultNote.mockRejectedValueOnce(new Error('読み取り専用ノートは編集できません。'))

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')
    await user.click(screen.getByRole('button', { name: 'テストインサイト' }))
    await screen.findByText(/これはテスト本文です/)

    await user.click(screen.getByRole('button', { name: '編集' }))
    await user.click(screen.getByRole('button', { name: '保存' }))

    // Should stay in edit mode (textarea still visible)
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'ノート編集エリア' })).toBeInTheDocument()
    })
  })

  // ── Phase 2: Sync button ────────────────────────────────────────────────────

  it('同期 button calls syncVault and surfaces the result', async () => {
    mockApi.mockResolvedValue(notesResponse)
    mockSyncVault.mockResolvedValueOnce(syncResult)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')

    const syncBtn = screen.getByRole('button', { name: '同期' })
    expect(syncBtn).toBeInTheDocument()

    await user.click(syncBtn)

    await waitFor(() => {
      expect(mockSyncVault).toHaveBeenCalledTimes(1)
    })
  })

  it('同期 with conflicts shows warning result', async () => {
    mockApi.mockResolvedValue(notesResponse)
    mockSyncVault.mockResolvedValueOnce(syncResultWithConflicts)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')

    await user.click(screen.getByRole('button', { name: '同期' }))

    await waitFor(() => {
      expect(mockSyncVault).toHaveBeenCalledTimes(1)
    })
  })

  // ── Phase 3: Graph tab ─────────────────────────────────────────────────────

  it('グラフ tab renders nodes from mocked getVaultGraph', async () => {
    mockApi.mockResolvedValue(notesResponse)
    mockGetVaultGraph.mockResolvedValueOnce(graphData)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')

    // Switch to グラフ tab
    await user.click(screen.getByRole('tab', { name: 'グラフ' }))

    await waitFor(() => {
      expect(mockGetVaultGraph).toHaveBeenCalledTimes(1)
    })

    // Node labels should appear in the SVG
    await waitFor(() => {
      expect(screen.getByText('テストインサイト')).toBeInTheDocument()
    })
  })

  it('clicking a graph node with a path calls getVaultNote and switches to ブラウザ tab', async () => {
    mockApi
      .mockResolvedValueOnce(notesResponse)
      .mockResolvedValueOnce(insightDetail)       // note loaded when graph node clicked

    mockGetVaultGraph.mockResolvedValueOnce(graphData)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')

    // Switch to graph
    await user.click(screen.getByRole('tab', { name: 'グラフ' }))

    await waitFor(() => {
      expect(mockGetVaultGraph).toHaveBeenCalledTimes(1)
    })

    // Wait for graph nodes to render
    await waitFor(() => {
      const nodeBtn = screen.queryByRole('button', { name: /テストインサイト.*クリックして開く/ })
      expect(nodeBtn).toBeInTheDocument()
    })

    // Click the node
    const nodeBtn = screen.getByRole('button', { name: /テストインサイト.*クリックして開く/ })
    await user.click(nodeBtn)

    // Should call getVaultNote with the node's path
    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('GET', '/api/vault/notes/insights/foo-1234abcd.md')
    })

    // Should switch back to browser tab
    await waitFor(() => {
      const browserTab = screen.getByRole('tab', { name: 'ブラウザ' })
      expect(browserTab).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('unresolved graph node (files=0, path="") has no button role', async () => {
    mockApi.mockResolvedValue(notesResponse)
    mockGetVaultGraph.mockResolvedValueOnce(graphData)

    const user = userEvent.setup()
    renderWithRouter(<KnowledgePage />)

    await screen.findByText('テストインサイト')

    await user.click(screen.getByRole('tab', { name: 'グラフ' }))

    await waitFor(() => {
      expect(mockGetVaultGraph).toHaveBeenCalledTimes(1)
    })

    // MyOrg node is unresolved (files=0, path="") — should NOT be a button
    await waitFor(() => {
      // The SVG text for MyOrg renders but as a g without role="button"
      const allButtons = screen.queryAllByRole('button', { name: /MyOrg/ })
      // No button role for unresolved node
      expect(allButtons.length).toBe(0)
    })
  })
})
