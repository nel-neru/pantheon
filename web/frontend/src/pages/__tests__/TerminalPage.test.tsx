import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TerminalPage } from '@/pages/TerminalPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// xterm.js は jsdom で動かないのでモック
vi.mock('@/components/TerminalView', () => ({
  TerminalView: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="terminal-view">{sessionId}</div>
  ),
}))

const execInfo = {
  modes: ['api', 'cli'],
  default_mode: 'api',
  current: { execution_mode: 'api', cli_tool: 'claude' },
  cli_tools: [
    { id: 'claude', label: 'Claude Code', resolved_command: 'claude', available: true, install_hint: '' },
    { id: 'codex', label: 'Codex CLI', resolved_command: 'codex', available: false, install_hint: 'npm i -g @openai/codex' },
  ],
}

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: 's1',
    name: 'shell',
    cwd: '/repo',
    command: ['bash'],
    status: 'running',
    exit_code: null,
    git_branch: 'main',
    created_at: '',
    waiting: false,
    ...overrides,
  }
}

describe('TerminalPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('shows the empty state and loads sessions + execution modes', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/terminal/sessions') return Promise.resolve({ sessions: [] })
      if (path === '/api/execution/modes') return Promise.resolve(execInfo)
      return Promise.reject(new Error(`unexpected ${method} ${path}`))
    })

    renderWithRouter(<TerminalPage />)

    expect(await screen.findByText('埋め込みターミナル')).toBeInTheDocument()
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('GET', '/api/terminal/sessions'))
    expect(mockApi).toHaveBeenCalledWith('GET', '/api/execution/modes')
  })

  it('renders existing sessions as workspace tabs with git branch', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/terminal/sessions') return Promise.resolve({ sessions: [session()] })
      if (path === '/api/execution/modes') return Promise.resolve(execInfo)
      return Promise.reject(new Error(`unexpected ${method} ${path}`))
    })

    renderWithRouter(<TerminalPage />)

    // git ブランチはタブ固有なので一意に検証できる
    expect(await screen.findByText('main')).toBeInTheDocument()
    expect(screen.getAllByText('shell').length).toBeGreaterThanOrEqual(1)
    // アクティブセッションのターミナルビュー(モック)が表示される
    expect(screen.getByTestId('terminal-view')).toHaveTextContent('s1')
  })

  it('creates a shell workspace from the menu', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (method === 'GET' && path === '/api/terminal/sessions') return Promise.resolve({ sessions: [] })
      if (method === 'GET' && path === '/api/execution/modes') return Promise.resolve(execInfo)
      if (method === 'POST' && path === '/api/terminal/sessions') {
        return Promise.resolve(session({ id: 'new1', name: 'shell' }))
      }
      return Promise.reject(new Error(`unexpected ${method} ${path}`))
    })

    renderWithRouter(<TerminalPage />)
    await screen.findByText('埋め込みターミナル')

    await userEvent.click(screen.getByRole('button', { name: /新規ワークスペース/ }))
    await userEvent.click(screen.getByRole('button', { name: 'シェル' }))

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/terminal/sessions', { name: 'shell' }),
    )
    expect(await screen.findByTestId('terminal-view')).toHaveTextContent('new1')
  })

  it('lists CLI agents in the create menu (available + unavailable)', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/terminal/sessions') return Promise.resolve({ sessions: [] })
      if (path === '/api/execution/modes') return Promise.resolve(execInfo)
      return Promise.reject(new Error(`unexpected ${method} ${path}`))
    })

    renderWithRouter(<TerminalPage />)
    await screen.findByText('埋め込みターミナル')
    await userEvent.click(screen.getByRole('button', { name: /新規ワークスペース/ }))

    expect(screen.getByRole('button', { name: /Claude Code/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Codex CLI/ })).toBeDisabled()
  })
})
