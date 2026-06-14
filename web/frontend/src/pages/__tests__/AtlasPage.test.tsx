import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AtlasPage } from '../AtlasPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const atlas = {
  generated_at: '2026-06-06T00:00:00+00:00',
  overview: {
    flows: 2,
    cli_commands: 41,
    api_routes: 59,
    websockets: 2,
    pages: 12,
    subsystems: 14,
    modules: 170,
    total_lines: 45880,
    total_files: 283,
  },
  flows: [
    {
      id: 'analyze-propose-approve-apply',
      name: '分析 → 提案 → 承認 → 適用',
      summary: '中核の改善ループ',
      trigger: { kind: 'cli', name: 'pantheon analyze' },
      steps: [{ component: 'agents/code_review_agent.py', action: '分析' }],
      surfaces: ['pantheon analyze', 'ProposalsPage'],
      verification: ['tests/test_policy_engine.py'],
      status: 'partial',
      known_issues: [{ severity: 'high', title: 'Web approve が PolicyEngine を通らない', file: 'web/server.py', detail: '詳細説明' }],
    },
    {
      id: 'atlas-introspection',
      name: 'Atlas（リポジトリ俯瞰可視化）',
      summary: 'コードベースを可視化',
      trigger: { kind: 'api', name: 'GET /api/atlas' },
      steps: [{ component: 'core/atlas/introspect.py', action: '集約' }],
      surfaces: ['pantheon atlas'],
      verification: ['tests/test_atlas.py'],
      status: 'solid',
      known_issues: [],
    },
  ],
  cli: [
    { command: 'pantheon atlas', group: 'atlas', handler: 'cmd_atlas', help: 'リポジトリ俯瞰', args: [{ name: '--json', required: false, help: '' }] },
    { command: 'pantheon analyze', group: 'analyze', handler: 'cmd_analyze', help: '分析', args: [] },
    { command: 'pantheon internal', group: 'internal', handler: null, help: '内部', args: [] },
  ],
  api: [
    { path: '/api/atlas', methods: ['GET'], name: 'api_atlas', kind: 'rest', tags: ['atlas'] },
    { path: '/ws/updates', methods: ['WS'], name: 'ws_updates', kind: 'websocket', tags: [] },
  ],
  frontend: { nav: [], routes: [], pages: [] },
  graph: {
    nodes: [
      { id: 'state', label: 'State / Models', files: 9 },
      { id: 'web-api', label: 'Web API', files: 1 },
    ],
    edges: [{ source: 'web-api', target: 'state', weight: 4 }],
    file_count: 170,
  },
  subsystems: [
    { id: 'cli', label: 'CLI', purpose: 'CLI エントリ', paths: ['main.py'], files: 10, lines: 1200 },
    { id: 'core', label: 'Core', purpose: 'コア', paths: ['core/'], files: 50, lines: 8000 },
  ],
}

describe('AtlasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('shows a loading state while the atlas is loading', () => {
    mockApi.mockReturnValue(new Promise(() => {}))
    renderWithRouter(<AtlasPage />)
    expect(screen.getByText('リポジトリを解析中…')).toBeInTheDocument()
  })

  it('renders the overview stat cards and flow health badges', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)

    expect(await screen.findByText('分析 → 提案 → 承認 → 適用')).toBeInTheDocument()
    expect(screen.getByText('Atlas（リポジトリ俯瞰可視化）')).toBeInTheDocument()
    // total_lines formatted with ja-JP thousands separator
    expect(screen.getByText('45,880')).toBeInTheDocument()
    // known issue title
    expect(screen.getByText('Web approve が PolicyEngine を通らない')).toBeInTheDocument()
    // status header badge buttons (title attribute distinguishes them from filter tabs)
    expect(screen.getByTitle('安定フローを表示')).toBeInTheDocument()
    expect(screen.getByTitle('一部課題フローを表示')).toBeInTheDocument()
  })

  it('shows Japanese severity labels for known issues', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // severity 'high' should show '高' not 'high'
    expect(screen.getByText('高')).toBeInTheDocument()
    expect(screen.queryByText('high')).not.toBeInTheDocument()
  })

  it('shows verification tags (not slash-joined text)', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // verification as badge/tag, not joined with ' / '
    expect(screen.getByText('tests/test_policy_engine.py')).toBeInTheDocument()
    // should not be slash-separated plain text
    expect(screen.queryByText(/tests\/test_policy_engine\.py \/ /)).not.toBeInTheDocument()
  })

  it('shows "検証なし" for flows with no verification', async () => {
    const atlasNoVerif = {
      ...atlas,
      flows: [
        {
          ...atlas.flows[1],
          verification: [],
        },
      ],
    }
    mockApi.mockResolvedValue(atlasNoVerif)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('Atlas（リポジトリ俯瞰可視化）')
    expect(screen.getByText(/検証なし/)).toBeInTheDocument()
  })

  it('shows surface tags with label "接点:"', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    expect(screen.getAllByText('接点:').length).toBeGreaterThan(0)
  })

  it('status header badges are clickable and filter flows tab', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // Click '安定' badge → should still show flows tab (now filtered to solid)
    const solidBadge = screen.getByTitle('安定フローを表示')
    await user.click(solidBadge)
    // Only solid flow visible
    expect(screen.getByText('Atlas（リポジトリ俯瞰可視化）')).toBeInTheDocument()
    expect(screen.queryByText('分析 → 提案 → 承認 → 適用')).not.toBeInTheDocument()
  })

  it('fragile badge is neutral when count is 0', async () => {
    const atlasNoFragile = { ...atlas, flows: atlas.flows.map((f) => ({ ...f, status: 'solid' as const })) }
    mockApi.mockResolvedValue(atlasNoFragile)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    const fragileBadge = screen.getByTitle('要注意フローを表示')
    expect(fragileBadge.className).toContain('badge-neutral')
    expect(fragileBadge.className).not.toContain('badge-red')
  })

  it('stat cards are clickable and switch to the corresponding tab', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // Click CLI stat card -> CLI tab
    const cliCard = screen.getByRole('button', { name: /CLI コマンド/ })
    await user.click(cliCard)
    expect(await screen.findByLabelText('CLI コマンド検索')).toBeInTheDocument()
  })

  it('switches to the CLI tab and filters commands (only handler-having commands shown)', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /CLI/ }))

    expect(await screen.findByText('pantheon atlas')).toBeInTheDocument()
    expect(screen.getByText('pantheon analyze')).toBeInTheDocument()
    // handler=null command should NOT appear
    expect(screen.queryByText('pantheon internal')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('CLI コマンド検索'), 'atlas')
    await waitFor(() => {
      expect(screen.queryByText('pantheon analyze')).not.toBeInTheDocument()
    })
    expect(screen.getByText('pantheon atlas')).toBeInTheDocument()
  })

  it('shows CLI count as filtered/total', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /CLI/ }))
    // Header shows "N / 全M件" - both handler-only commands (2)
    expect(await screen.findByText(/全2件/)).toBeInTheDocument()
  })

  it('shows empty row message when CLI search has no results', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /CLI/ }))
    await user.type(screen.getByLabelText('CLI コマンド検索'), 'xxxxxxxxx')
    await waitFor(() => {
      expect(screen.getByText('該当コマンドなし')).toBeInTheDocument()
    })
  })

  it('clear button removes CLI search filter', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /CLI/ }))
    await user.type(screen.getByLabelText('CLI コマンド検索'), 'atlas')
    await waitFor(() => expect(screen.queryByText('pantheon analyze')).not.toBeInTheDocument())

    await user.click(screen.getByLabelText('検索をクリア'))
    await waitFor(() => expect(screen.getByText('pantheon analyze')).toBeInTheDocument())
  })

  it('switches to the API tab and shows routes', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /API/ }))

    expect(await screen.findByText('/api/atlas')).toBeInTheDocument()
    expect(screen.getByText('/ws/updates')).toBeInTheDocument()
  })

  it('shows empty row message when API search has no results', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /API/ }))
    await user.type(screen.getByLabelText('API ルート検索'), 'xxxxxxxxx')
    await waitFor(() => {
      expect(screen.getByText('該当ルートなし')).toBeInTheDocument()
    })
  })

  it('switches to subsystems tab and shows sortable table', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /サブシステム/ }))

    expect(await screen.findByText('CLI エントリ')).toBeInTheDocument()
    // formatNumber applied: 8,000
    expect(screen.getByText('8,000')).toBeInTheDocument()
  })

  it('expands subsystem row to show paths', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /サブシステム/ }))

    // CLI エントリ is in purpose column, uniquely in subsystem table
    const purposeCell = await screen.findByText('CLI エントリ')
    await user.click(purposeCell.closest('tr')!)
    expect(await screen.findByText('main.py')).toBeInTheDocument()
  })

  it('shows an error state with retry button on initial load failure', async () => {
    mockApi.mockRejectedValue(new Error('atlas boom'))
    renderWithRouter(<AtlasPage />)

    await waitFor(() => {
      expect(screen.getByText('Atlas の読み込みに失敗しました')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })

  it('preserves existing atlas data on quiet re-fetch failure (toast only, no error screen)', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')

    // Now fail on re-fetch (quiet)
    mockApi.mockRejectedValue(new Error('re-fetch failed'))
    const refreshBtn = screen.getByRole('button', { name: '更新' })
    await user.click(refreshBtn)

    // Atlas data should still be visible (not replaced by error screen)
    await waitFor(() => {
      expect(screen.getByText('分析 → 提案 → 承認 → 適用')).toBeInTheDocument()
    })
    // Error screen should NOT appear
    expect(screen.queryByText('Atlas の読み込みに失敗しました')).not.toBeInTheDocument()
  })

  it('shows the dependency graph tab with accessible adjacency list', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    expect(await screen.findByText('モジュール依存グラフ')).toBeInTheDocument()
    // Adjacency list (in details/summary)
    expect(screen.getByText('依存関係テキスト一覧')).toBeInTheDocument()
    expect(screen.getAllByText(/State \/ Models/).length).toBeGreaterThan(0)
  })

  it('graph nodes are keyboard-focusable with aria-label', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // Nodes rendered as role="button" with aria-label
    const nodeButtons = screen.getAllByRole('button', { name: /ファイル/ })
    expect(nodeButtons.length).toBeGreaterThan(0)
  })

  it('graph node is highlighted on focus and toggles on keyboard Enter', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // Find the "State / Models" node button
    const stateNode = screen.getByRole('button', { name: /State \/ Models.*ファイル/ })
    // onFocus fires when focused → aria-pressed = true (focus highlight)
    await act(() => { stateNode.focus() })
    expect(stateNode).toHaveAttribute('aria-pressed', 'true')
    // Press Enter → toggles off (since focus already set it)
    await user.keyboard('{Enter}')
    expect(stateNode).toHaveAttribute('aria-pressed', 'false')
    // Press Enter again → toggles back on
    await user.keyboard('{Enter}')
    expect(stateNode).toHaveAttribute('aria-pressed', 'true')
  })

  it('zoom controls are present with accessible labels', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // Zoom group
    expect(screen.getByRole('group', { name: 'ズーム操作' })).toBeInTheDocument()
    // Zoom in/out buttons
    expect(screen.getByRole('button', { name: '拡大' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '縮小' })).toBeInTheDocument()
    // Zoom out disabled at default level
    expect(screen.getByRole('button', { name: '縮小' })).toBeDisabled()
    // Zoom in enabled at default level
    expect(screen.getByRole('button', { name: '拡大' })).not.toBeDisabled()
  })

  it('zoom in button increases zoom and shows reset button', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // No reset button at default zoom
    expect(screen.queryByRole('button', { name: 'ズームをリセット' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '拡大' }))
    // After zoom in, zoom-out button enabled and reset shown
    expect(screen.getByRole('button', { name: '縮小' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'ズームをリセット' })).toBeInTheDocument()

    // Reset brings back to default
    await user.click(screen.getByRole('button', { name: 'ズームをリセット' }))
    expect(screen.queryByRole('button', { name: 'ズームをリセット' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '縮小' })).toBeDisabled()
  })

  it('zoom in is disabled at max zoom level', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // Click zoom in 3 times (4 levels total: 0→1→2→3)
    await user.click(screen.getByRole('button', { name: '拡大' }))
    await user.click(screen.getByRole('button', { name: '拡大' }))
    await user.click(screen.getByRole('button', { name: '拡大' }))
    // At max level, zoom in disabled
    expect(screen.getByRole('button', { name: '拡大' })).toBeDisabled()
  })

  it('graph SVG aria-label includes node count', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /依存グラフ/ }))

    await screen.findByText('モジュール依存グラフ')
    // SVG group has aria-label with node count
    const svgGroup = screen.getByRole('group', { name: /サブシステム依存グラフ/ })
    expect(svgGroup).toBeInTheDocument()
    expect(svgGroup.getAttribute('aria-label')).toContain('2 ノード')
  })

  it('uses RefreshButton with label "更新" (not "再読み込み")', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    expect(screen.getByRole('button', { name: '更新' })).toBeInTheDocument()
    expect(screen.queryByText('再読み込み')).not.toBeInTheDocument()
  })

  it('flow status filter tabs filter the flows list', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // Click '安定' filter tab
    const solidFilterTab = screen.getByRole('tab', { name: /安定/ })
    await user.click(solidFilterTab)

    await waitFor(() => {
      expect(screen.queryByText('分析 → 提案 → 承認 → 適用')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Atlas（リポジトリ俯瞰可視化）')).toBeInTheDocument()
  })

  it('generated_at uses formatDateTime (not raw ISO)', async () => {
    // Use a recent timestamp so the date is not flagged as stale (isStale=false → shows '生成:')
    const recentIso = new Date(Date.now() - 30 * 60 * 1000).toISOString() // 30 min ago
    mockApi.mockResolvedValue({ ...atlas, generated_at: recentIso })
    renderWithRouter(<AtlasPage />)
    await screen.findByText('分析 → 提案 → 承認 → 適用')
    // Should NOT show raw ISO string
    expect(screen.queryByText(recentIso)).not.toBeInTheDocument()
    // Should show a formatted date with the '生成:' prefix (non-stale path)
    expect(screen.getByText(/生成:/)).toBeInTheDocument()
  })
})
