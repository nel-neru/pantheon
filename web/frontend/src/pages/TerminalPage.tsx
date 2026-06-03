import { useCallback, useEffect, useRef, useState } from 'react'
import { GitBranch, Plus, TerminalSquare, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'

import { TerminalView } from '@/components/TerminalView'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

type Session = {
  id: string
  name: string
  cwd: string
  command: string[]
  status: string
  exit_code: number | null
  git_branch: string | null
  created_at: string
  waiting: boolean
}

type CliTool = {
  id: string
  label: string
  resolved_command: string
  available: boolean
  install_hint: string
}

type ExecutionInfo = {
  modes: string[]
  default_mode: string
  current: { execution_mode: string; cli_tool: string }
  cli_tools: CliTool[]
}

function basename(path: string): string {
  const parts = path.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || path
}

export function TerminalPage() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [execInfo, setExecInfo] = useState<ExecutionInfo | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  const loadSessions = useCallback(async () => {
    try {
      const data = await api<{ sessions: Session[] }>('GET', '/api/terminal/sessions')
      setSessions(data.sessions)
      setActiveId((current) => current ?? (data.sessions[0]?.id ?? null))
    } catch {
      /* terminal endpoints are localhost-only; ignore transient errors */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSessions()
    api<ExecutionInfo>('GET', '/api/execution/modes')
      .then(setExecInfo)
      .catch(() => setExecInfo(null))
  }, [loadSessions])

  // セッションの status/waiting を定期更新（cmux 風のライブ表示）
  useEffect(() => {
    const timer = window.setInterval(() => void loadSessions(), 4000)
    return () => window.clearInterval(timer)
  }, [loadSessions])

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const createSession = async (payload: { cli_tool?: string; command?: string; name?: string }) => {
    setCreating(true)
    setMenuOpen(false)
    try {
      const session = await api<Session>('POST', '/api/terminal/sessions', payload)
      setSessions((current) => [...current, session])
      setActiveId(session.id)
      toast.success(`ワークスペース「${session.name}」を起動しました`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ターミナルの起動に失敗しました。')
    } finally {
      setCreating(false)
    }
  }

  const killSession = async (id: string) => {
    try {
      await api('DELETE', `/api/terminal/sessions/${id}`)
    } catch {
      /* ignore */
    }
    setSessions((current) => {
      const next = current.filter((s) => s.id !== id)
      setActiveId((active) => (active === id ? next[0]?.id ?? null : active))
      return next
    })
  }

  const active = sessions.find((s) => s.id === activeId) ?? null

  return (
    <>
      <header className="page-header">
        <div className="page-title">ターミナル</div>
        <div className="page-actions">
          {execInfo ? (
            <span className="badge badge-neutral" title="設定の実行モード">
              モード: {execInfo.current.execution_mode === 'cli' ? 'CLI' : 'API'}
            </span>
          ) : null}
          <div className="terminal-create" ref={menuRef}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setMenuOpen((v) => !v)}
              disabled={creating}
            >
              <Plus size={14} />
              新規ワークスペース
            </button>
            {menuOpen ? (
              <div className="terminal-create-menu" role="menu">
                <button type="button" className="terminal-create-item" onClick={() => void createSession({ name: 'shell' })}>
                  <TerminalSquare size={14} />
                  シェル
                </button>
                <div className="terminal-create-label">CLI エージェント</div>
                {(execInfo?.cli_tools ?? []).map((tool) => (
                  <button
                    key={tool.id}
                    type="button"
                    className="terminal-create-item"
                    disabled={!tool.available}
                    title={tool.available ? tool.resolved_command : `未インストール: ${tool.install_hint}`}
                    onClick={() => void createSession({ cli_tool: tool.id, name: tool.label })}
                  >
                    <TerminalSquare size={14} />
                    {tool.label}
                    {tool.available ? null : <span className="badge badge-neutral text-xs">未検出</span>}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="page-content terminal-page">
        <aside className="terminal-tabs" aria-label="ワークスペース">
          {sessions.length === 0 ? (
            <div className="terminal-tabs-empty text-sm text-muted">
              ワークスペースがありません。「新規ワークスペース」で開始してください。
            </div>
          ) : null}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              className={cn('terminal-tab', session.id === activeId && 'active', session.waiting && 'waiting')}
              onClick={() => setActiveId(session.id)}
            >
              <span className={cn('status-dot', session.status === 'running' ? 'connected' : 'connecting')} />
              <span className="terminal-tab-body">
                <span className="terminal-tab-name">{session.name}</span>
                <span className="terminal-tab-meta">
                  {session.git_branch ? (
                    <span className="terminal-tab-branch">
                      <GitBranch size={10} />
                      {session.git_branch}
                    </span>
                  ) : (
                    basename(session.cwd)
                  )}
                </span>
              </span>
              <span
                role="button"
                tabIndex={0}
                aria-label="ワークスペースを閉じる"
                className="terminal-tab-close"
                onClick={(event) => {
                  event.stopPropagation()
                  void killSession(session.id)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.stopPropagation()
                    void killSession(session.id)
                  }
                }}
              >
                <X size={12} />
              </span>
            </button>
          ))}
        </aside>

        <section className="terminal-pane">
          {active ? (
            <>
              <div className="terminal-pane-header">
                <div className="terminal-pane-title">
                  <TerminalSquare size={14} />
                  <span className="font-medium">{active.name}</span>
                  <span className="mono text-xs text-muted">{active.cwd}</span>
                  {active.status !== 'running' ? (
                    <span className="badge badge-neutral text-xs">終了 (code {active.exit_code ?? '?'})</span>
                  ) : null}
                </div>
                <button type="button" className="btn btn-ghost btn-icon" aria-label="終了" onClick={() => void killSession(active.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <TerminalView key={active.id} sessionId={active.id} onExit={() => void loadSessions()} />
            </>
          ) : (
            <div className="terminal-empty">
              <TerminalSquare className="empty-state-icon" size={32} />
              <h3>埋め込みターミナル</h3>
              <p className="text-muted text-sm">
                {loading ? '読み込み中…' : 'ワークスペースを作成すると、ここに実シェルや CLI エージェントが表示されます。'}
              </p>
            </div>
          )}
        </section>
      </div>
    </>
  )
}
