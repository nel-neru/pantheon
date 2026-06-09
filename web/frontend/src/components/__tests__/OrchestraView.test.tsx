import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OrchestraView } from '../OrchestraView'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

describe('OrchestraView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('renders the sessions tree, agents and the handoff flywheel', async () => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/dashboard/orchestra') {
        return {
          sessions: [
            {
              id: 's1',
              name: 'MyApp',
              status: 'running',
              driver: 'headless',
              agents: [
                {
                  agent_id: 'a1',
                  title: 'analyze#1',
                  role: 'analyze',
                  status: 'running',
                  exit_code: null,
                },
              ],
            },
          ],
          handoffs: [
            {
              id: 'h1',
              source: 'SNS運用',
              target: 'note販売',
              kind: 'audience_signal',
              status: 'pending',
              title: 'バズ導線の引き渡し',
              priority: 'high',
            },
          ],
          counts: { sessions: 1, active_sessions: 1, agents: 1, handoffs: 1, pending_handoffs: 1 },
        }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<OrchestraView />)

    expect(await screen.findByText('MyApp')).toBeInTheDocument()
    expect(screen.getByText('analyze#1')).toBeInTheDocument()
    expect(screen.getByText('SNS運用')).toBeInTheDocument()
    expect(screen.getByText('note販売')).toBeInTheDocument()
    expect(screen.getByText('バズ導線の引き渡し')).toBeInTheDocument()
  })

  it('shows an empty state without throwing when the request fails', async () => {
    mockApi.mockImplementation(async () => {
      throw new Error('boom')
    })

    renderWithRouter(<OrchestraView />)

    expect(await screen.findByText(/実行中のセッションはありません/)).toBeInTheDocument()
    expect(screen.getByText('組織横断の引き渡しはまだありません。')).toBeInTheDocument()
  })
})
