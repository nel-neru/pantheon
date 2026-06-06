import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { AtlasPage } from '../AtlasPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as { error: ReturnType<typeof vi.fn> }

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
      known_issues: [{ severity: 'high', title: 'Web approve が PolicyEngine を通らない', file: 'web/server.py' }],
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

  it('renders the overview and flow health with status + known issues', async () => {
    mockApi.mockResolvedValue(atlas)
    renderWithRouter(<AtlasPage />)

    expect(await screen.findByText('分析 → 提案 → 承認 → 適用')).toBeInTheDocument()
    expect(screen.getByText('Atlas（リポジトリ俯瞰可視化）')).toBeInTheDocument()
    // overview stat value
    expect(screen.getByText('45,880')).toBeInTheDocument()
    // known issue surfaces
    expect(screen.getByText('Web approve が PolicyEngine を通らない')).toBeInTheDocument()
    // status header counts
    expect(screen.getByText('1 安定')).toBeInTheDocument()
    expect(screen.getByText('1 一部課題')).toBeInTheDocument()
  })

  it('switches to the CLI tab and filters commands', async () => {
    mockApi.mockResolvedValue(atlas)
    const user = userEvent.setup()
    renderWithRouter(<AtlasPage />)

    await screen.findByText('分析 → 提案 → 承認 → 適用')
    await user.click(screen.getByRole('tab', { name: /CLI/ }))

    expect(await screen.findByText('pantheon atlas')).toBeInTheDocument()
    expect(screen.getByText('pantheon analyze')).toBeInTheDocument()

    await user.type(screen.getByLabelText('CLI コマンド検索'), 'atlas')
    await waitFor(() => {
      expect(screen.queryByText('pantheon analyze')).not.toBeInTheDocument()
    })
    expect(screen.getByText('pantheon atlas')).toBeInTheDocument()
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

  it('shows an error state and retries on failure', async () => {
    mockApi.mockRejectedValue(new Error('atlas boom'))
    renderWithRouter(<AtlasPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('atlas boom')
    })
    expect(await screen.findByText('Atlas の読み込みに失敗しました')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })
})
