import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ChatPage } from '../ChatPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
}

type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

type SessionDetail = {
  id: string
  name: string
  created_at: string
  updated_at: string
  messages: StoredMessage[]
}

function createChatApiMock(initialSessions: SessionDetail[], hasLlm = true) {
  const sessions = [...initialSessions]
  let createdCount = 0
  let messageCount = 0

  const toSummary = (session: SessionDetail) => ({
    id: session.id,
    name: session.name,
    created_at: session.created_at,
    updated_at: session.updated_at,
    message_count: session.messages.length,
  })

  return async (method: string, path: string, body?: unknown) => {
    if (method === 'GET' && path === '/api/platform/status') {
      return { has_llm: hasLlm }
    }

    if (method === 'GET' && path === '/api/chat/sessions') {
      return { sessions: sessions.map(toSummary) }
    }

    if (method === 'POST' && path === '/api/chat/sessions') {
      createdCount += 1
      const session = {
        id: `created-${createdCount}`,
        name: '新しいセッション',
        created_at: '2026-05-28T17:00:00Z',
        updated_at: '2026-05-28T17:00:00Z',
        messages: [],
      }
      sessions.unshift(session)
      return { ...session, messages: [...session.messages] }
    }

    const sessionMatch = path.match(/^\/api\/chat\/sessions\/([^/]+)$/)
    if (method === 'GET' && sessionMatch) {
      const session = sessions.find((item) => item.id === sessionMatch[1])
      if (!session) throw new Error('セッションが見つかりません')
      return { ...session, messages: [...session.messages] }
    }

    if (method === 'PUT' && sessionMatch) {
      const session = sessions.find((item) => item.id === sessionMatch[1])
      if (!session) throw new Error('セッションが見つかりません')
      session.name = (body as { name: string }).name
      session.updated_at = '2026-05-28T17:02:00Z'
      return { id: session.id, name: session.name }
    }

    if (method === 'DELETE' && sessionMatch) {
      const index = sessions.findIndex((item) => item.id === sessionMatch[1])
      if (index === -1) throw new Error('セッションが見つかりません')
      sessions.splice(index, 1)
      return { status: 'ok' }
    }

    const messageMatch = path.match(/^\/api\/chat\/sessions\/([^/]+)\/messages$/)
    if (method === 'POST' && messageMatch) {
      const session = sessions.find((item) => item.id === messageMatch[1])
      if (!session) throw new Error('セッションが見つかりません')

      messageCount += 1
      const text = (body as { content: string }).content
      const userMessage = {
        id: `user-${messageCount}`,
        role: 'user' as const,
        content: text,
        timestamp: '2026-05-28T17:05:00Z',
      }
      const assistantMessage = {
        id: `assistant-${messageCount}`,
        role: 'assistant' as const,
        content: `応答: ${text}`,
        timestamp: '2026-05-28T17:05:01Z',
      }

      if (session.messages.length === 0 && session.name === '新しいセッション') {
        session.name = text.slice(0, 20) + (text.length > 20 ? '...' : '')
      }

      session.messages = [...session.messages, userMessage, assistantMessage]
      session.updated_at = '2026-05-28T17:05:01Z'
      return { user_message: userMessage, assistant_message: assistantMessage }
    }

    throw new Error(`Unexpected request: ${method} ${path}`)
  }
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('renders the session sidebar and new session button', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: 'レビュー依頼',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        },
      ]),
    )

    renderWithRouter(<ChatPage />)

    expect(await screen.findByRole('button', { name: '新規' })).toBeInTheDocument()
    expect(screen.getByLabelText('チャットセッション')).toBeInTheDocument()
    expect(screen.getByText('レビュー依頼')).toBeInTheDocument()
    expect(await screen.findByText('LLM 準備完了')).toBeInTheDocument()
  })

  it('auto creates a session when none exist', async () => {
    mockApi.mockImplementation(createChatApiMock([]))

    renderWithRouter(<ChatPage />)

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/chat/sessions', { name: '' })
    })
    expect(await screen.findByText('新しいセッション')).toBeInTheDocument()
  })

  it('shows an error toast when platform status loading fails', async () => {
    mockApi.mockImplementation(async (method, path) => {
      if (method === 'GET' && path === '/api/platform/status') {
        throw new Error('status load failed')
      }
      if (method === 'GET' && path === '/api/chat/sessions') {
        return { sessions: [] }
      }
      if (method === 'POST' && path === '/api/chat/sessions') {
        return {
          id: 'session-1',
          name: '新しいセッション',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        }
      }
      throw new Error(`Unexpected request: ${method} ${path}`)
    })

    renderWithRouter(<ChatPage />)

    await waitFor(() => {
      expect(mockedToast.error).toHaveBeenCalledWith('status load failed')
    })
  })

  it('shows slash command suggestions', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: '既存セッション',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        },
      ]),
    )
    const user = userEvent.setup()

    renderWithRouter(<ChatPage />)

    const input = await screen.findByPlaceholderText('プラットフォーム、組織、ゴールについて Pantheon に問い合わせてください')
    await user.type(input, '/')

    expect(screen.getByRole('listbox', { name: 'スラッシュコマンド' })).toBeInTheDocument()
    expect(screen.getByText('/help')).toBeInTheDocument()
    expect(screen.getByText('/analyze')).toBeInTheDocument()
    expect(screen.getByText('/goal')).toBeInTheDocument()
    expect(screen.getByText('/agents')).toBeInTheDocument()
  })

  it('sends a message through the session API and renders the response', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: '新しいセッション',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        },
      ]),
    )
    const user = userEvent.setup()

    renderWithRouter(<ChatPage />)

    const input = await screen.findByPlaceholderText('プラットフォーム、組織、ゴールについて Pantheon に問い合わせてください')
    await user.type(input, 'テストメッセージ')
    await user.click(screen.getByRole('button', { name: '送信' }))

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/chat/sessions/session-1/messages', {
        content: 'テストメッセージ',
        role: 'user',
      })
    })
    expect(await screen.findByText('応答: テストメッセージ')).toBeInTheDocument()
    expect(screen.getByText('あなた')).toBeInTheDocument()
    expect(screen.getByText('Pantheon')).toBeInTheDocument()
  })

  it('loads messages when switching sessions', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: '最初のセッション',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [
            {
              id: 'm1',
              role: 'assistant',
              content: '最初のメッセージ',
              timestamp: '2026-05-28T17:00:00Z',
            },
          ],
        },
        {
          id: 'session-2',
          name: '別のセッション',
          created_at: '2026-05-28T17:10:00Z',
          updated_at: '2026-05-28T17:10:00Z',
          messages: [
            {
              id: 'm2',
              role: 'assistant',
              content: '別の会話',
              timestamp: '2026-05-28T17:10:00Z',
            },
          ],
        },
      ]),
    )
    const user = userEvent.setup()

    renderWithRouter(<ChatPage />)

    expect(await screen.findByText('最初のメッセージ')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '別のセッション' }))

    expect(await screen.findByText('別の会話')).toBeInTheDocument()
  })

  it('renames a session when saving with Enter', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: '元の名前',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        },
      ]),
    )
    const user = userEvent.setup()

    renderWithRouter(<ChatPage />)

    await user.click(await screen.findByRole('button', { name: '元の名前 の名前を編集' }))
    const input = screen.getByDisplayValue('元の名前')
    await user.clear(input)
    await user.type(input, '新しい名前{enter}')

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith('PUT', '/api/chat/sessions/session-1', { name: '新しい名前' })
    })
    expect(await screen.findByText('新しい名前')).toBeInTheDocument()
  })

  it('cancels session renaming with Escape', async () => {
    mockApi.mockImplementation(
      createChatApiMock([
        {
          id: 'session-1',
          name: '元の名前',
          created_at: '2026-05-28T17:00:00Z',
          updated_at: '2026-05-28T17:00:00Z',
          messages: [],
        },
      ]),
    )
    const user = userEvent.setup()

    renderWithRouter(<ChatPage />)

    await user.click(await screen.findByRole('button', { name: '元の名前 の名前を編集' }))
    const input = screen.getByDisplayValue('元の名前')
    await user.clear(input)
    await user.type(input, 'キャンセル{Escape}')

    await waitFor(() => {
      expect(screen.queryByDisplayValue('キャンセル')).not.toBeInTheDocument()
    })
    expect(screen.getByText('元の名前')).toBeInTheDocument()
    expect(
      mockApi.mock.calls.filter(
        ([method, path]) => method === 'PUT' && path === '/api/chat/sessions/session-1',
      ),
    ).toHaveLength(0)
  })
})
