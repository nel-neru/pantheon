import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { Target } from 'lucide-react'

import { streamSse } from '@/lib/api'
import { PageHeader } from '@/components/PageHeader'

// SSE イベントの型定義（バックエンドのディスクリミネート型と対応）
type StartEvent = {
  type: 'start'
  goal: string
  org_name: string | null
}

type ProgressEvent = {
  type: 'progress'
  done: number
  total: number
  failed: number
  progress_pct: number
  message: string
  content: string
}

type ResultEvent = {
  type: 'result'
  goal: string
  org_name: string | null
  result: string
  summary: string
  content: string
  data: Record<string, unknown>
}

type DoneEvent = {
  type: 'done'
  goal: string
  org_name: string | null
  result: string
  content: string
}

type ErrorEvent = {
  type: 'error'
  message: string
}

type GoalSseEvent = StartEvent | ProgressEvent | ResultEvent | DoneEvent | ErrorEvent

// ワイヤーから来る unknown を型ガードで絞り込む
function toGoalEvent(ev: Record<string, unknown>): GoalSseEvent | null {
  const t = ev.type
  if (t === 'start') {
    return {
      type: 'start',
      goal: typeof ev.goal === 'string' ? ev.goal : '',
      org_name: typeof ev.org_name === 'string' ? ev.org_name : null,
    }
  }
  if (t === 'progress') {
    return {
      type: 'progress',
      done: typeof ev.done === 'number' ? ev.done : 0,
      total: typeof ev.total === 'number' ? ev.total : 0,
      failed: typeof ev.failed === 'number' ? ev.failed : 0,
      progress_pct: typeof ev.progress_pct === 'number' ? ev.progress_pct : 0,
      message: typeof ev.message === 'string' ? ev.message : '',
      content: typeof ev.content === 'string' ? ev.content : '',
    }
  }
  if (t === 'result') {
    return {
      type: 'result',
      goal: typeof ev.goal === 'string' ? ev.goal : '',
      org_name: typeof ev.org_name === 'string' ? ev.org_name : null,
      result: typeof ev.result === 'string' ? ev.result : '',
      summary: typeof ev.summary === 'string' ? ev.summary : '',
      content: typeof ev.content === 'string' ? ev.content : '',
      data:
        ev.data !== null && typeof ev.data === 'object' && !Array.isArray(ev.data)
          ? (ev.data as Record<string, unknown>)
          : {},
    }
  }
  if (t === 'done') {
    return {
      type: 'done',
      goal: typeof ev.goal === 'string' ? ev.goal : '',
      org_name: typeof ev.org_name === 'string' ? ev.org_name : null,
      result: typeof ev.result === 'string' ? ev.result : '',
      content: typeof ev.content === 'string' ? ev.content : '',
    }
  }
  if (t === 'error') {
    return {
      type: 'error',
      message: typeof ev.message === 'string' ? ev.message : 'エラーが発生しました。',
    }
  }
  return null
}

type RunState =
  | { phase: 'idle' }
  | { phase: 'running'; goal: string; orgName: string | null; progress: ProgressEvent | null }
  | {
      phase: 'done'
      goal: string
      orgName: string | null
      result: string
      summary: string
    }
  | { phase: 'error'; message: string }

export function GoalsPage() {
  const [goalText, setGoalText] = useState('')
  const [runState, setRunState] = useState<RunState>({ phase: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  // アンマウント時に実行中のリクエストを中断する
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const isRunning = runState.phase === 'running'
  const canSubmit = !isRunning && goalText.trim().length > 0

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return

    // 前回の状態をリセット
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunState({ phase: 'running', goal: goalText.trim(), orgName: null, progress: null })

    try {
      await streamSse(
        '/api/goals/stream',
        { goal_text: goalText.trim() },
        (ev) => {
          // 中断済み（中止ボタン or 別実行で置換）の run からの遅延コールバックは破棄する。
          // controller.signal.aborted は「中止→idle 後の同一 run の遅延イベント」も捕捉する。
          if (controller.signal.aborted) return

          const event = toGoalEvent(ev)
          if (!event) return

          if (event.type === 'start') {
            setRunState((prev) =>
              prev.phase === 'running'
                ? { ...prev, goal: event.goal, orgName: event.org_name }
                : prev,
            )
          } else if (event.type === 'progress') {
            setRunState((prev) =>
              prev.phase === 'running' ? { ...prev, progress: event } : prev,
            )
          } else if (event.type === 'result') {
            setRunState({
              phase: 'done',
              goal: event.goal,
              orgName: event.org_name,
              result: event.result,
              summary: event.summary,
            })
          } else if (event.type === 'done') {
            setRunState((prev) => {
              // result イベントが先行していれば done は既に phase:'done' のはず
              if (prev.phase === 'done') return prev
              return {
                phase: 'done',
                goal: event.goal,
                orgName: event.org_name,
                result: event.result,
                summary: '',
              }
            })
          } else if (event.type === 'error') {
            setRunState({ phase: 'error', message: event.message })
          }
        },
        controller.signal,
      )
    } catch (err) {
      // 後続の実行に置き換えられた古い run の失敗は、現在の状態に触れない
      if (abortRef.current !== controller) return
      // AbortError は中止操作なのでエラー表示しない
      if (err instanceof Error && err.name === 'AbortError') {
        setRunState({ phase: 'idle' })
        return
      }
      const message =
        err instanceof Error ? err.message : 'ゴールの実行に失敗しました。'
      setRunState({ phase: 'error', message })
    }
  }, [canSubmit, goalText])

  const handleAbort = () => {
    abortRef.current?.abort()
    setRunState({ phase: 'idle' })
  }

  return (
    <>
      <PageHeader
        title="ゴール実行"
        subtitle="抽象的なゴールを入力するとエージェントがタスクに分解してライブ実行します。"
      />

      <div className="page-content flex flex-col gap-4">
        {/* 入力エリア */}
        <div className="card">
          <div className="card-body flex flex-col gap-3">
            <label className="input-label" htmlFor="goal-input">
              ゴールを入力
            </label>
            <textarea
              id="goal-input"
              className="input"
              rows={4}
              maxLength={4000}
              placeholder="例: コードベースの品質を向上させる提案を作成してください"
              value={goalText}
              onChange={(e) => setGoalText(e.target.value)}
              disabled={isRunning}
              aria-label="ゴールテキスト"
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted text-sm">{goalText.length} / 4000 文字</span>
              <div className="flex gap-2">
                {isRunning ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleAbort}
                  >
                    中止
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleSubmit()}
                  disabled={!canSubmit}
                >
                  {isRunning ? '実行中…' : '実行'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 実行中の進捗 */}
        {runState.phase === 'running' ? (
          <div className="card" role="status" aria-live="polite">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Target size={16} className="text-muted" aria-hidden="true" />
                <span className="font-medium text-sm">
                  {runState.goal || 'ゴールを解析中…'}
                </span>
                {runState.orgName ? (
                  <span className="badge badge-neutral">{runState.orgName}</span>
                ) : null}
              </div>

              {runState.progress ? (
                <>
                  <div className="flex items-center justify-between text-sm text-muted">
                    <span>{runState.progress.message || 'タスクを実行中…'}</span>
                    <span>
                      {runState.progress.done}/{runState.progress.total}
                      {runState.progress.failed > 0 ? (
                        <span className="text-red-500 ml-1">
                          （失敗 {runState.progress.failed}）
                        </span>
                      ) : null}
                    </span>
                  </div>
                  <div
                    className="goals-progress-track"
                    role="progressbar"
                    aria-valuenow={runState.progress.progress_pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="進捗"
                  >
                    <div
                      className="goals-progress-fill"
                      style={{ '--progress-pct': `${runState.progress.progress_pct}%` } as CSSProperties}
                    />
                  </div>
                </>
              ) : (
                <div className="text-muted text-sm">エージェント組織を起動中…</div>
              )}
            </div>
          </div>
        ) : null}

        {/* 完了結果 */}
        {runState.phase === 'done' ? (
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Target size={16} className="text-muted" aria-hidden="true" />
                <span className="font-medium text-sm">{runState.goal}</span>
                {runState.orgName ? (
                  <span className="badge badge-neutral">{runState.orgName}</span>
                ) : null}
                <span className="badge badge-success ml-auto">完了</span>
              </div>
              {runState.summary ? (
                <div className="text-sm text-muted">{runState.summary}</div>
              ) : null}
              <pre className="knowledge-preview whitespace-pre-wrap">
                {runState.result || '（結果なし）'}
              </pre>
            </div>
          </div>
        ) : null}

        {/* エラー */}
        {runState.phase === 'error' ? (
          <div className="card border-red-500/30" role="alert">
            <div className="card-body">
              <div className="text-sm font-medium text-red-500">エラー</div>
              <div className="text-sm text-muted mt-1">{runState.message}</div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  )
}
