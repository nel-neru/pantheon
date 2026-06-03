import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CoreImprovePanel } from '@/components/CoreImprovePanel'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

describe('CoreImprovePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('submits instruction + file path and shows the validated proposal result', async () => {
    mockApi.mockResolvedValue({
      validated: true,
      applied: false,
      file_path: 'core/llm/base.py',
      change_summary: 'docstring を追加',
      diff: '--- a/core/llm/base.py\n+++ b/core/llm/base.py\n',
      attempts: 1,
      proposal_id: 'p-1',
      org_name: 'RepoCorp-Self',
      policy_decision: 'human_required',
      policy_reason: 'core/ は人間確認',
    })
    const onProposed = vi.fn()
    renderWithRouter(<CoreImprovePanel onProposed={onProposed} />)

    await userEvent.type(screen.getByLabelText('対象ファイル（リポジトリ相対パス）'), 'core/llm/base.py')
    await userEvent.type(screen.getByLabelText('改善指示'), 'docstring を追加')
    await userEvent.click(screen.getByRole('button', { name: /Core を改善/ }))

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/core/improve', {
        instruction: 'docstring を追加',
        file_path: 'core/llm/base.py',
      }),
    )
    expect(await screen.findByText('検証済み（テスト緑）')).toBeInTheDocument()
    expect(screen.getByText('人間承認待ち')).toBeInTheDocument()
    expect(onProposed).toHaveBeenCalledWith('RepoCorp-Self')
  })

  it('blocks submission and shows a validation error when fields are empty', async () => {
    renderWithRouter(<CoreImprovePanel />)
    await userEvent.click(screen.getByRole('button', { name: /Core を改善/ }))
    expect(await screen.findByText(/両方を入力/)).toBeInTheDocument()
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('shows an error banner when the API call fails', async () => {
    mockApi.mockRejectedValue(new Error('LLM クライアントが未設定です。'))
    renderWithRouter(<CoreImprovePanel />)
    await userEvent.type(screen.getByLabelText('対象ファイル（リポジトリ相対パス）'), 'core/x.py')
    await userEvent.type(screen.getByLabelText('改善指示'), 'do something')
    await userEvent.click(screen.getByRole('button', { name: /Core を改善/ }))
    expect(await screen.findByText('LLM クライアントが未設定です。')).toBeInTheDocument()
  })
})
