import { useCallback, useEffect, useRef, useState } from 'react'
import { History, Target } from 'lucide-react'
import { toast } from 'sonner'

import { api, streamSSE } from '@/lib/api'
import { formatDate } from '@/lib/utils'

type Organization = {
  name: string
}

type GoalHistoryItem = {
  goal: string
  result: string
  timestamp: string
}

type LogEntry = {
  id: string
  text: string
  tone: 'line' | 'done' | 'error'
}

function describeGoalEvent(event: Record<string, unknown>) {
  const type = typeof event.type === 'string' ? event.type : 'progress'

  if (type === 'start') return `${String(event.org_name ?? 'プラットフォーム全体')} のゴール実行を開始します`
  if (type === 'result') return String(event.result ?? event.content ?? 'ゴール実行の結果が生成されました')
  if (type === 'done') return String(event.content ?? 'ゴール実行が完了しました')
  if (type === 'error') return String(event.content ?? event.message ?? 'ゴール実行に失敗しました')
  return String(event.content ?? event.message ?? 'ゴールを実行中です')
}

export function GoalsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [history, setHistory] = useState<GoalHistoryItem[]>([])
  const [goalText, setGoalText] = useState('')
  const [selectedOrg, setSelectedOrg] = useState('')
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [result, setResult] = useState('')
  const controllerRef = useRef<AbortController | null>(null)

  const loadHistory = useCallback(async () => {
    try {
      const data = await api<GoalHistoryItem[]>('GET', '/api/goals/history')
      setHistory(data)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ゴール履歴の読み込みに失敗しました。')
    }
  }, [])

  const loadOrganizations = useCallback(async () => {
    try {
      const data = await api<Organization[]>('GET', '/api/organizations')
      setOrganizations(data)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '組織の読み込みに失敗しました。')
    }
  }, [])

  useEffect(() => {
    void Promise.all([loadOrganizations(), loadHistory()])
    return () => controllerRef.current?.abort()
  }, [loadHistory, loadOrganizations])

  const appendLog = useCallback((text: string, tone: LogEntry['tone'] = 'line') => {
    setLogs((current) => [...current, { id: crypto.randomUUID(), text, tone }])
  }, [])

  const handleRun = () => {
    if (!goalText.trim()) {
      toast.error('実行前にゴールを入力してください。')
      return
    }

    controllerRef.current?.abort()
    setRunning(true)
    setLogs([])
    setResult('')

    controllerRef.current = streamSSE(
      '/api/goals/stream',
      {
        goal_text: goalText.trim(),
        org_name: selectedOrg || undefined,
      },
      (event) => {
        const type = typeof event.type === 'string' ? event.type : 'progress'
        const text = describeGoalEvent(event)
        appendLog(text, type === 'done' ? 'done' : type === 'error' ? 'error' : 'line')

        if (type === 'result') {
          setResult(String(event.result ?? event.content ?? ''))
        }

        if (type === 'done') {
          setRunning(false)
          void loadHistory()
          toast.success('ゴールの実行が完了しました。')
        }

        if (type === 'error') {
          setRunning(false)
          toast.error(text)
        }
      },
      () => {
        setRunning(false)
      },
      (error) => {
        setRunning(false)
        appendLog(error.message, 'error')
        toast.error(error.message)
      },
    )
  }

  return (
    <>
      <header className="page-header">
        <div className="page-title">ゴール</div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">ゴールを実行</div>
              <div className="card-description">ストリーミング更新付きでゴール指向ワークフローを実行します。</div>
            </div>
          </div>
          <div className="card-body flex flex-col gap-4">
            <div className="input-group">
              <label className="input-label" htmlFor="goal-text">
                ゴールテキスト
              </label>
              <textarea
                id="goal-text"
                className="textarea"
                value={goalText}
                onChange={(event) => setGoalText(event.target.value)}
                placeholder="ゴールを記述してください…"
              />
            </div>

            <div className="grid-2">
              <div className="input-group">
                <label className="input-label" htmlFor="goal-org">
                  対象組織
                </label>
                <select
                  id="goal-org"
                  className="select"
                  value={selectedOrg}
                  onChange={(event) => setSelectedOrg(event.target.value)}
                >
                  <option value="">プラットフォーム全体</option>
                  {organizations.map((org) => (
                    <option key={org.name} value={org.name}>
                      {org.name}
                    </option>
                  ))}
                </select>
              </div>

            </div>

            <div>
              <button type="button" className="btn btn-primary" onClick={handleRun} disabled={running}>
                <Target size={14} />
                {running ? '実行中' : '実行'}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">進捗ログ</div>
              <div className="card-description">リアルタイムのゴール実行イベントです。</div>
            </div>
          </div>
          <div className="card-body">
            {logs.length === 0 ? (
              <div className="empty-state">
                <Target className="empty-state-icon" size={28} />
                <h3>まだ実行アクティビティがありません</h3>
                <p>ゴールを実行すると、オーケストレーションの進捗と最終結果を確認できます。</p>
              </div>
            ) : (
              <div className="progress-log">
                {logs.map((log) => (
                  <div
                    key={log.id}
                    className={
                      log.tone === 'done'
                        ? 'log-done'
                        : log.tone === 'error'
                          ? 'log-error'
                          : 'log-line'
                    }
                  >
                    {log.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {result ? (
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">結果</div>
                <div className="card-description">直近のゴール実行の出力です。</div>
              </div>
            </div>
            <div className="card-body">
              <div className="text-fg2">{result}</div>
            </div>
          </div>
        ) : null}

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">履歴</div>
              <div className="card-description">これまでに実行したゴールとその出力です。</div>
            </div>
          </div>
          <div className="card-body">
            {history.length === 0 ? (
              <div className="empty-state">
                <History className="empty-state-icon" size={28} />
                <h3>まだゴール履歴がありません</h3>
                <p>実行したゴールがここに表示されます。</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ゴール</th>
                      <th>結果</th>
                      <th>日時</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => (
                      <tr key={`${item.goal}-${item.timestamp}`}>
                        <td>{item.goal}</td>
                        <td>{item.result}</td>
                        <td>{formatDate(item.timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
