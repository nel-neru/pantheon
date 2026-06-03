import { useState } from 'react'
import { CheckCircle, Wrench } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'

type CoreImproveResult = {
  validated: boolean
  applied: boolean
  file_path: string
  change_summary: string
  diff: string
  attempts: number
  proposal_id: string
  org_name: string
  policy_decision: string
  policy_reason: string
}

function policyLabel(decision: string): string {
  if (decision === 'human_required') return '人間承認待ち'
  if (decision === 'auto_approve') return '自動承認可'
  if (decision === 'reject') return '自動却下'
  return decision
}

export function CoreImprovePanel({ onProposed }: { onProposed?: (orgName: string) => void }) {
  const [instruction, setInstruction] = useState('')
  const [filePath, setFilePath] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<CoreImproveResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!instruction.trim() || !filePath.trim()) {
      setError('改善指示と対象ファイルパスの両方を入力してください。')
      return
    }
    setSubmitting(true)
    setError(null)
    setResult(null)
    try {
      const res = await api<CoreImproveResult>('POST', '/api/core/improve', {
        instruction: instruction.trim(),
        file_path: filePath.trim(),
      })
      setResult(res)
      toast.success(`検証済みの改善提案を作成しました（${policyLabel(res.policy_decision)}）`)
      onProposed?.(res.org_name)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Core 改善の依頼に失敗しました。'
      setError(message)
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title flex items-center gap-2">
            <Wrench size={16} />
            Core 自己改善（実験的）
          </div>
          <div className="card-description">
            RepoCorp 自身のコードを、契約中の任意の LLM で改善します。内蔵エージェントが編集→既存テストで検証（必要なら反復）し、
            検証済みの変更を「人間承認待ち」の改善提案として登録します。作業ツリーへ自動適用はしません。
          </div>
        </div>
      </div>
      <form onSubmit={submit} className="card-body flex flex-col gap-4">
        <div className="input-group">
          <label className="input-label" htmlFor="core-improve-file">
            対象ファイル（リポジトリ相対パス）
          </label>
          <input
            id="core-improve-file"
            className="input mono"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            placeholder="例: core/llm/base.py"
            autoComplete="off"
          />
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor="core-improve-instruction">
            改善指示
          </label>
          <textarea
            id="core-improve-instruction"
            className="textarea"
            rows={3}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="例: generate_json に max_tokens 引数を追加し docstring を補強する"
          />
        </div>

        {error ? (
          <div className="settings-status-bar warn">
            <span className="badge badge-red">エラー</span>
            <span className="text-sm text-muted">{error}</span>
          </div>
        ) : null}

        {result ? (
          <div className="settings-status-bar ok flex-col items-start gap-2" style={{ alignItems: 'flex-start' }}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="badge badge-green">
                <CheckCircle size={10} />
                検証済み（テスト緑）
              </span>
              <span className="badge badge-yellow">{policyLabel(result.policy_decision)}</span>
              <span className="text-sm text-muted">
                {result.org_name} に提案を作成（{result.attempts} 回の試行）
              </span>
            </div>
            {result.change_summary ? (
              <div className="text-sm text-fg2">{result.change_summary}</div>
            ) : null}
            {result.diff ? (
              <pre className="progress-log" style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto' }}>
                {result.diff}
              </pre>
            ) : null}
          </div>
        ) : null}

        <div>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            <Wrench size={14} />
            {submitting ? '検証中…（テスト実行）' : 'Core を改善（検証して提案）'}
          </button>
        </div>
      </form>
    </div>
  )
}
