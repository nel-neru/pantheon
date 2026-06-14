import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { AgentsPage } from '../AgentsPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
}

const agent = {
  name: 'Planner',
  capability_id: 'planner',
  skills: ['analysis', 'planning'],
  description: 'Plans work',
  implementation: 'python',
}

const skill = {
  name: 'analysis',
  description: 'Analyzes repositories',
  persona: 'analyst',
  focus: 'quality',
}

const runtimeAgent = {
  id: 'rt-1',
  name: 'RuntimePlanner',
  organization: 'Org1',
  division: 'Div1',
  team: 'Team1',
  skills: ['analysis'],
  status: 'running',
  current_task: null,
  proficiency: 75,
  configuration: {},
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('shows a loading state while registry data is loading', async () => {
    const request = deferred<[typeof agent[], typeof skill[]]>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') {
        return request.promise.then(([agents]) => agents)
      }
      if (method === 'GET' && path === '/api/skills') {
        return request.promise.then(([, skills]) => skills)
      }
      if (method === 'GET' && path === '/api/agents/runtime') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AgentsPage />)

    expect(screen.getByText('エージェントレジストリを読み込み中…')).toBeInTheDocument()

    request.resolve([[], []])
    await waitFor(() => {
      expect(screen.getByText('エージェントが見つかりません')).toBeInTheDocument()
    })
  })

  it('renders empty states when no agents or skills exist', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return []
      if (method === 'GET' && path === '/api/skills') return []
      if (method === 'GET' && path === '/api/agents/runtime') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('エージェントが見つかりません')).toBeInTheDocument()
    expect(screen.getByText('スキルが見つかりません')).toBeInTheDocument()
    expect(screen.getByText('ルーティング未分析')).toBeInTheDocument()
  })

  it('shows an error toast and inline error state when the registry request fails', async () => {
    mockApi.mockRejectedValue(new Error('agent load failed'))

    renderWithRouter(<AgentsPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('agent load failed')
    })
    expect(await screen.findByText('レジストリの読み込みに失敗しました')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })

  it('renders agent and skill data', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return [agent]
      if (method === 'GET' && path === '/api/skills') return [skill]
      if (method === 'GET' && path === '/api/agents/runtime') return []
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('Planner')).toBeInTheDocument()
    expect(screen.getByText('planning')).toBeInTheDocument()
    expect(screen.getByText('quality')).toBeInTheDocument()
    expect(screen.queryByText('ルーティング未分析')).toBeInTheDocument()
  })

  it('shows an analyzing state while orchestration analysis is running', async () => {
    const request = deferred<{ task_type: string; analysis: { complexity: string } }>()
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return [agent]
      if (method === 'GET' && path === '/api/skills') return [skill]
      if (method === 'GET' && path === '/api/agents/runtime') return []
      if (method === 'GET' && path === '/api/orchestration/analyze/analysis') return request.promise
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('Planner')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '分析' }))

    expect(screen.getByRole('button', { name: '分析中…' })).toBeDisabled()

    request.resolve({ task_type: 'analysis', analysis: { complexity: 'low' } })
    expect(await screen.findByText('複雑さ:')).toBeInTheDocument()
  })

  it('runs orchestration analysis and displays the result', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return [agent]
      if (method === 'GET' && path === '/api/skills') return [skill]
      if (method === 'GET' && path === '/api/agents/runtime') return []
      if (method === 'GET' && path === '/api/orchestration/analyze/goal_execution') {
        return {
          task_type: 'goal_execution',
          analysis: {
            complexity: 'high',
            recommended_agent_ids: ['planner', 'reviewer'],
            notes: 'Needs coordination',
          },
        }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('Planner')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox'), 'goal_execution')
    await user.click(screen.getByRole('button', { name: '分析' }))

    expect(await screen.findByText('高')).toBeInTheDocument()
    // 'planner' resolves to 'Planner (planner)' via agent name resolution; 'reviewer' has no match so stays raw
    expect(screen.getByText('Planner (planner)')).toBeInTheDocument()
    expect(screen.getByText('reviewer')).toBeInTheDocument()
    // 'notes' is shown in structured display (key-value dd)
    expect(screen.getByText('Needs coordination')).toBeInTheDocument()
  })

  it('renders runtime agents with Japanese status labels', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return []
      if (method === 'GET' && path === '/api/skills') return []
      if (method === 'GET' && path === '/api/agents/runtime') return [runtimeAgent]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('RuntimePlanner')).toBeInTheDocument()
    // status 'running' must be shown as Japanese label from lib/labels
    expect(screen.getByText('実行中')).toBeInTheDocument()
    // ScoreBar renders the score value
    expect(screen.getByText('75')).toBeInTheDocument()
  })

  it('opens the config modal when the settings button is clicked', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return []
      if (method === 'GET' && path === '/api/skills') return []
      if (method === 'GET' && path === '/api/agents/runtime') return [
        { ...runtimeAgent, configuration: { timeout: 30, model: 'claude' } },
      ]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    const user = userEvent.setup()
    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('RuntimePlanner')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /設定/ }))

    // Modal title should appear
    expect(screen.getByText('RuntimePlanner のランタイム設定')).toBeInTheDocument()
    // Key-value structured display
    expect(screen.getByText('timeout')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('shows split running/idle counts in header badges', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/agents') return []
      if (method === 'GET' && path === '/api/skills') return []
      if (method === 'GET' && path === '/api/agents/runtime') return [
        { ...runtimeAgent, status: 'running' },
        { ...runtimeAgent, id: 'rt-2', name: 'IdleAgent', status: 'idle' },
      ]
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<AgentsPage />)

    expect(await screen.findByText('稼働 1')).toBeInTheDocument()
    expect(screen.getByText('待機 1')).toBeInTheDocument()
  })
})
