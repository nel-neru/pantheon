import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowRight, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { api, streamSSE } from '@/lib/api'

type Organization = {
  name: string
}

type AnalysisResult = {
  org_name: string
  files_reviewed: number
  proposals_generated: number
}

type LogEntry = {
  id: string
  text: string
  tone: 'line' | 'done' | 'error'
}

function describeEvent(event: Record<string, unknown>) {
  const type = typeof event.type === 'string' ? event.type : 'progress'

  if (type === 'start') return `${String(event.org_name ?? '選択した組織')} の分析を開始します`
  if (type === 'proposal') return `提案を生成しました: ${String(event.title ?? event.content ?? '無題の提案')}`
  if (type === 'done') {
    return `${Number(event.files_reviewed ?? 0)} 件のファイルを確認し、${Number(event.proposals_generated ?? 0)} 件の提案を生成しました`
  }
  if (type === 'error') return String(event.content ?? event.message ?? '分析に失敗しました')
  return String(event.content ?? event.message ?? '分析を実行中です')
}

export function AnalyzePage() {
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [maxFiles, setMaxFiles] = useState('')
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const loadOrganizations = useCallback(async () => {
    try {
      const data = await api<Organization[]>('GET', '/api/organizations')
      setOrganizations(data)
      setSelectedOrg((current) => (current && data.some((org) => org.name === current) ? current : data[0]?.name || ''))
      setLoadError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : '組織の読み込みに失敗しました。'
      setOrganizations([])
      setSelectedOrg('')
      setLoadError(message)
      toast.error(message)
    }
  }, [])

  useEffect(() => {
    void loadOrganizations()
    return () => controllerRef.current?.abort()
  }, [loadOrganizations])

  const appendLog = useCallback((text: string, tone: LogEntry['tone'] = 'line') => {
    setLogs((current) => [...current, { id: crypto.randomUUID(), text, tone }])
  }, [])

  const proposalsCount = useMemo(() => result?.proposals_generated ?? 0, [result])

  const handleRun = () => {
    if (!selectedOrg) {
      toast.error('分析を実行する前に組織を選択してください。')
      return
    }

    controllerRef.current?.abort()
    setRunning(true)
    setLogs([])
    setResult(null)

    controllerRef.current = streamSSE(
      '/api/analyze/stream',
      {
        org_name: selectedOrg,
        max_files: maxFiles ? Number(maxFiles) : undefined,
      },
      (event) => {
        const type = typeof event.type === 'string' ? event.type : 'progress'
        const text = describeEvent(event)
        appendLog(text, type === 'done' ? 'done' : type === 'error' ? 'error' : 'line')

        if (type === 'proposal') {
          setResult((current) => ({
            org_name: selectedOrg,
            files_reviewed: current?.files_reviewed ?? 0,
            proposals_generated: (current?.proposals_generated ?? 0) + 1,
          }))
        }

        if (type === 'done') {
          setResult({
            org_name: String(event.org_name ?? selectedOrg),
            files_reviewed: Number(event.files_reviewed ?? 0),
            proposals_generated: Number(event.proposals_generated ?? 0),
          })
          setRunning(false)
          toast.success('分析が完了しました。')
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
        <div className="page-title">分析</div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">分析を実行</div>
              <div className="card-description">リポジトリ分析の進捗をリアルタイムで表示します。</div>
            </div>
          </div>
          <div className="card-body flex flex-col gap-4">
            {loadError ? (
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>組織の読み込みに失敗しました</h3>
                <p>{loadError}</p>
                <button type="button" className="btn btn-secondary" onClick={() => void loadOrganizations()}>
                  再試行
                </button>
              </div>
            ) : organizations.length === 0 ? (
              <div className="empty-state">
                <Search className="empty-state-icon" size={28} />
                <h3>分析対象の組織がありません</h3>
                <p>まず組織を作成すると、ここからリポジトリ分析を開始できます。</p>
              </div>
            ) : (
              <>
                <div className="grid-2">
                  <div className="input-group">
                    <label className="input-label" htmlFor="analysis-org">
                      対象組織
                    </label>
                    <select
                      id="analysis-org"
                      className="select"
                      value={selectedOrg}
                      onChange={(event) => setSelectedOrg(event.target.value)}
                    >
                      {organizations.map((org) => (
                        <option key={org.name} value={org.name}>
                          {org.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="input-group">
                    <label className="input-label" htmlFor="analysis-max-files">
                      最大ファイル数
                    </label>
                    <input
                      id="analysis-max-files"
                      className="input"
                      type="number"
                      min="1"
                      value={maxFiles}
                      onChange={(event) => setMaxFiles(event.target.value)}
                      placeholder="任意の上限"
                    />
                  </div>
                </div>

                <div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleRun}
                    disabled={running || !selectedOrg}
                  >
                    <Search size={14} />
                    {running ? '実行中' : '分析を実行'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">進捗ログ</div>
              <div className="card-description">分析エンジンから配信される進捗イベントです。</div>
            </div>
          </div>
          <div className="card-body">
            {logs.length === 0 ? (
              <div className="empty-state">
                <Search className="empty-state-icon" size={28} />
                <h3>まだ分析アクティビティがありません</h3>
                <p>分析を開始すると、進捗、提案、最終件数を確認できます。</p>
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
                <div className="card-title">分析結果</div>
                <div className="card-description">直近に完了した分析の概要です。</div>
              </div>
            </div>
            <div className="card-body flex flex-col gap-4">
              <div className="metrics-grid">
                <div className="metric-card">
                  <div className="metric-label">対象組織</div>
                  <div className="metric-value">{result.org_name}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">確認ファイル数</div>
                  <div className="metric-value">{result.files_reviewed}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">生成された提案</div>
                  <div className="metric-value">{proposalsCount}</div>
                </div>
              </div>
              <div>
                <Link className="btn btn-secondary" to={`/proposals?org=${encodeURIComponent(result.org_name)}`}>
                  <ArrowRight size={14} />
                  提案を見る
                </Link>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  )
}
