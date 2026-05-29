import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Command, Pencil, Plus, Send, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type PlatformStatus = {
  has_llm: boolean
}

type ChatSession = {
  id: string
  name: string
  created_at: string
  updated_at: string
  message_count: number
}

type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

type ChatSessionDetail = {
  id: string
  name: string
  created_at: string
  updated_at: string
  messages: StoredMessage[]
}

type ChatMessageResponse = {
  user_message: StoredMessage
  assistant_message: StoredMessage
}

type SlashCommand = {
  command: string
  description: string
}

const INPUT_PLACEHOLDER = 'プラットフォーム、組織、ゴールについて RepoCorp AI に問い合わせてください'

const slashCommands: SlashCommand[] = [
  { command: 'help', description: '利用可能なコマンドと使い方を表示します。' },
  { command: 'init', description: 'プラットフォームを初期化します。' },
  { command: 'orgs', description: '登録済みの Organization 一覧を表示します。' },
  { command: 'add', description: 'Organization を追加します。例: /add demo ./repo' },
  { command: 'analyze', description: 'リポジトリ分析ワークフローを開始します。' },
  { command: 'proposals', description: '最新の改善提案を確認します。' },
  { command: 'approve', description: '提案を承認します。例: /approve <id> <org>' },
  { command: 'goal', description: '抽象ゴールを実行します。例: /goal テストを増やす' },
  { command: 'status', description: 'プラットフォームとデーモンの状態を確認します。' },
  { command: 'agents', description: '登録済みエージェント一覧を確認します。' },
]

function renderInline(line: string) {
  return line
    .split(/(`[^`]+`|\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((part, index) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>
      }

      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
      }

      return <Fragment key={`${part}-${index}`}>{part}</Fragment>
    })
}

function renderMessage(content: string): ReactNode {
  const lines = content.split('\n')

  return lines.map((line, index) => (
    <Fragment key={`${line}-${index}`}>
      {renderInline(line)}
      {index < lines.length - 1 ? <br /> : null}
    </Fragment>
  ))
}

export function ChatPage() {
  const [input, setInput] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [platformStatus, setPlatformStatus] = useState<PlatformStatus | null>(null)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<StoredMessage[]>([])
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [sending, setSending] = useState(false)
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const messagesRef = useRef<HTMLDivElement | null>(null)
  const currentSessionIdRef = useRef<string | null>(null)
  const editInputRef = useRef<HTMLInputElement | null>(null)
  const skipBlurSaveRef = useRef(false)

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) ?? null,
    [currentSessionId, sessions],
  )

  const loadSessions = useCallback(async () => {
    const result = await api<{ sessions: ChatSession[] }>('GET', '/api/chat/sessions')
    setSessions(result.sessions)
    return result.sessions
  }, [])

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    const session = await api<ChatSessionDetail>('GET', `/api/chat/sessions/${sessionId}`)
    if (currentSessionIdRef.current === sessionId) {
      setMessages(session.messages ?? [])
    }
    return session
  }, [])

  const selectSession = useCallback(
    async (sessionId: string) => {
      currentSessionIdRef.current = sessionId
      setCurrentSessionId(sessionId)
      await loadSessionMessages(sessionId)
    },
    [loadSessionMessages],
  )

  const createSession = useCallback(async () => {
    const session = await api<ChatSessionDetail>('POST', '/api/chat/sessions', { name: '' })
    currentSessionIdRef.current = session.id
    setCurrentSessionId(session.id)
    setMessages(session.messages ?? [])
    await loadSessions()
    return session
  }, [loadSessions])

  const deleteSession = useCallback(
    async (sessionId: string) => {
      const isCurrent = currentSessionIdRef.current === sessionId

      try {
        await api('DELETE', `/api/chat/sessions/${sessionId}`)
        if (editingSessionId === sessionId) {
          setEditingSessionId(null)
          setEditingName('')
        }
        const nextSessions = await loadSessions()

        if (!isCurrent) {
          return
        }

        if (nextSessions.length > 0) {
          await selectSession(nextSessions[0].id)
          return
        }

        currentSessionIdRef.current = null
        setCurrentSessionId(null)
        setMessages([])
        await createSession()
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'セッションの削除に失敗しました。')
      }
    },
    [createSession, editingSessionId, loadSessions, selectSession],
  )

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const status = await api<PlatformStatus>('GET', '/api/platform/status')
        setPlatformStatus(status)
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'プラットフォーム状態の読み込みに失敗しました。')
      }
    }

    void loadStatus()
  }, [])

  useEffect(() => {
    const initializeSessions = async () => {
      setLoadingSessions(true)
      try {
        const loadedSessions = await loadSessions()
        if (loadedSessions.length > 0) {
          await selectSession(loadedSessions[0].id)
        } else {
          await createSession()
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'チャットセッションの読み込みに失敗しました。')
      } finally {
        setLoadingSessions(false)
      }
    }

    void initializeSessions()
  }, [createSession, loadSessions, selectSession])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }, [input])

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const filteredCommands = useMemo(() => {
    if (!input.startsWith('/')) return []
    const query = input.slice(1).split(/\s/)[0].toLowerCase()
    return slashCommands.filter(({ command }) => command.includes(query))
  }, [input])

  const showCommands = input.startsWith('/') && !input.includes('\n') && filteredCommands.length > 0

  useEffect(() => {
    setSelectedIndex(0)
  }, [input])

  const cancelEditSession = useCallback(() => {
    setEditingSessionId(null)
    setEditingName('')
  }, [])

  const startEditSession = useCallback((session: ChatSession, event: React.MouseEvent) => {
    event.stopPropagation()
    event.preventDefault()
    skipBlurSaveRef.current = false
    setEditingSessionId(session.id)
    setEditingName(session.name)
    window.setTimeout(() => {
      editInputRef.current?.focus()
      editInputRef.current?.select()
    }, 0)
  }, [])

  const confirmEditSession = useCallback(async () => {
    if (!editingSessionId) return

    const trimmedName = editingName.trim()
    if (!trimmedName) {
      cancelEditSession()
      toast.error('セッション名は空にできません')
      return
    }

    try {
      await api('PUT', `/api/chat/sessions/${editingSessionId}`, { name: trimmedName })
      setSessions((current) =>
        current.map((session) =>
          session.id === editingSessionId ? { ...session, name: trimmedName } : session,
        ),
      )
    } catch {
      toast.error('セッション名の更新に失敗しました')
    } finally {
      cancelEditSession()
    }
  }, [cancelEditSession, editingName, editingSessionId])

  const applyCommand = (command: SlashCommand) => {
    setInput(`/${command.command} `)
    textareaRef.current?.focus()
  }

  const sendMessage = useCallback(
    async (text: string) => {
      let sessionId = currentSessionIdRef.current
      if (!sessionId) {
        const session = await createSession()
        sessionId = session.id
      }
      if (!sessionId) return

      const tempId = `temp-${crypto.randomUUID()}`
      const tempUserMessage: StoredMessage = {
        id: tempId,
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      }

      if (currentSessionIdRef.current === sessionId) {
        setMessages((current) => [...current, tempUserMessage])
      }

      setSending(true)
      try {
        const result = await api<ChatMessageResponse>('POST', `/api/chat/sessions/${sessionId}/messages`, {
          content: text,
          role: 'user',
        })

        if (currentSessionIdRef.current === sessionId) {
          setMessages((current) => [
            ...current.filter((message) => message.id !== tempId),
            result.user_message,
            result.assistant_message,
          ])
        }

        await loadSessions()
      } catch (error) {
        if (currentSessionIdRef.current === sessionId) {
          setMessages((current) => current.filter((message) => message.id !== tempId))
        }
        toast.error(error instanceof Error ? error.message : 'メッセージの送信に失敗しました。')
      } finally {
        setSending(false)
      }
    },
    [createSession, loadSessions],
  )

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending) return

    setInput('')
    await sendMessage(text)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showCommands && event.key === 'ArrowDown') {
      event.preventDefault()
      setSelectedIndex((current) => (current + 1) % filteredCommands.length)
      return
    }

    if (showCommands && event.key === 'ArrowUp') {
      event.preventDefault()
      setSelectedIndex((current) =>
        current === 0 ? filteredCommands.length - 1 : current - 1,
      )
      return
    }

    if (showCommands && event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      applyCommand(filteredCommands[selectedIndex])
      return
    }

    if (event.key === 'Escape' && showCommands) {
      event.preventDefault()
      setInput('')
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <div className="page-title">チャット</div>
          <p className="page-subtitle">
            {currentSession ? `${currentSession.name} の会話履歴を保存しています。` : 'セッションごとに会話履歴を保存します。'}
          </p>
        </div>
        <div className="page-actions">
          <div className="badge badge-neutral">{sessions.length} セッション</div>
          <div className={`badge ${platformStatus?.has_llm ? 'badge-green' : 'badge-neutral'}`}>
            {platformStatus?.has_llm ? 'LLM 準備完了' : 'LLM オフライン'}
          </div>
        </div>
      </header>

      <div className="page-content chat-page-content">
        <div className="card chat-card">
          <div className="chat-page">
            <aside className="chat-sidebar" aria-label="チャットセッション">
              <div className="chat-sidebar-header">
                <div className="chat-sidebar-title">チャット</div>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => void createSession()}>
                  <Plus size={14} />
                  新規
                </button>
              </div>

              <div className="chat-session-list">
                {sessions.map((session) => (
                  <div key={session.id} className={`chat-session-item ${session.id === currentSessionId ? 'active' : ''}`}>
                    {editingSessionId === session.id ? (
                      <div className="chat-session-select chat-session-editing" onClick={(event) => event.stopPropagation()}>
                        <input
                          ref={editInputRef}
                          className="chat-session-name-input"
                          value={editingName}
                          onChange={(event) => setEditingName(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.preventDefault()
                              void confirmEditSession()
                            }
                            if (event.key === 'Escape') {
                              event.preventDefault()
                              skipBlurSaveRef.current = true
                              cancelEditSession()
                            }
                          }}
                          onBlur={() => {
                            if (skipBlurSaveRef.current) {
                              skipBlurSaveRef.current = false
                              return
                            }
                            void confirmEditSession()
                          }}
                          onClick={(event) => event.stopPropagation()}
                        />
                        <span className="chat-session-count">{session.message_count}</span>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="chat-session-select"
                        aria-label={session.name || '無題のセッション'}
                        onClick={() => void selectSession(session.id)}
                      >
                        <span
                          className="chat-session-name"
                          title={session.name || '無題のセッション'}
                          onDoubleClick={(event) => startEditSession(session, event)}
                        >
                          {session.name || '無題のセッション'}
                        </span>
                        <span className="chat-session-count">{session.message_count}</span>
                      </button>
                    )}
                    {editingSessionId !== session.id ? (
                      <button
                        type="button"
                        className="chat-session-edit btn btn-ghost btn-icon"
                        aria-label={`${session.name || '無題のセッション'} の名前を編集`}
                        title="名前を編集"
                        onClick={(event) => startEditSession(session, event)}
                      >
                        <Pencil size={12} />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="chat-session-delete btn btn-ghost btn-sm btn-icon"
                      aria-label={`${session.name || '無題のセッション'} を削除`}
                      onClick={(event) => {
                        event.stopPropagation()
                        void deleteSession(session.id)
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}

                {!loadingSessions && sessions.length === 0 ? (
                  <div className="chat-session-empty">セッションがありません</div>
                ) : null}
              </div>
            </aside>

            <div className="chat-main">
              <div ref={messagesRef} className="chat-messages">
                {messages.length === 0 ? (
                  <div className="empty-state flex-1">
                    <Bot className="empty-state-icon" size={28} />
                    <h3>{loadingSessions ? 'セッションを準備中' : '会話を始める'}</h3>
                    <p>
                      {loadingSessions
                        ? '保存済みセッションを読み込んでいます。'
                        : 'メッセージ履歴はセッションごとに保存され、リロード後も引き継がれます。'}
                    </p>
                  </div>
                ) : null}

                {messages.map((message) => (
                  <div key={message.id} className={`chat-msg ${message.role}`}>
                    <div className="chat-msg-meta">{message.role === 'user' ? 'あなた' : 'RepoCorp AI'}</div>
                    <div className="chat-msg-body">{renderMessage(message.content)}</div>
                  </div>
                ))}

                {sending ? (
                  <div className="chat-typing" aria-label="応答中">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                ) : null}
              </div>

              <div className="chat-input-area">
                <div className="chat-input-wrap">
                  {showCommands ? (
                    <div className="slash-dropdown" role="listbox" aria-label="スラッシュコマンド">
                      {filteredCommands.map((command, index) => (
                        <button
                          key={command.command}
                          type="button"
                          className={`slash-item ${index === selectedIndex ? 'selected' : ''}`}
                          onMouseDown={(event) => {
                            event.preventDefault()
                            applyCommand(command)
                          }}
                        >
                          <Command size={14} className="text-accent" />
                          <div>
                            <div className="slash-cmd">/{command.command}</div>
                            <div className="slash-desc">{command.description}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null}

                  <textarea
                    ref={textareaRef}
                    className="chat-input"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={INPUT_PLACEHOLDER}
                    rows={1}
                  />
                  <button
                    type="button"
                    className="chat-send-btn"
                    onClick={() => void handleSend()}
                    disabled={!input.trim() || sending || !currentSessionId}
                    aria-label="送信"
                  >
                    <Send size={15} />
                  </button>
                </div>
                <div className="chat-hint">/ でコマンド  •  Enter で送信  •  Shift+Enter で改行</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
