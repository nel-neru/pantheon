import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ContentSchedulePage } from '../ContentSchedulePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const mockedToast = toast as unknown as {
  error: ReturnType<typeof vi.fn>
  success: ReturnType<typeof vi.fn>
}

const job = {
  job_id: 'abc12345',
  org_name: 'SNS Growth',
  kind: 'content_brief',
  theme: '朝活',
  interval_seconds: 86400,
  enabled: true,
  last_run_at: null,
  next_run_at: null,
  last_status: 'scheduled',
  last_detail: '',
  run_count: 0,
  publish_platform: '',
  publish_mode: 'assisted',
}

const failedJob = {
  ...job,
  job_id: 'fail123',
  last_status: 'error',
  last_detail: 'Claude rate-limited during generation',
  run_count: 5,
}

const stoppedDaemon = {
  running: false,
  pid: null,
  rate_limited: false,
  retry_at: null,
  cycle_count: 0,
  interval_seconds: null,
}

const runningDaemon = {
  running: true,
  pid: 1234,
  rate_limited: false,
  retry_at: null,
  cycle_count: 3,
  interval_seconds: 600,
}

function routeGet(jobs: (typeof job)[], daemon = stoppedDaemon) {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return jobs
    if (method === 'GET' && path === '/api/organizations')
      return [{ name: 'SNS Growth', target_repo_path: '/repo/sns' }]
    if (method === 'GET' && path === '/api/content-daemon/status') return daemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'POST' && path === '/api/content-jobs') return job
    throw new Error(`Unexpected ${method} ${path}`)
  })
}

beforeEach(() => {
  mockApi.mockReset()
  mockedToast.error.mockReset()
  mockedToast.success.mockReset()
})

// ---- 基本描画 ----------------------------------------------------------------

it('lists content jobs and shows the stopped PDCA badge', async () => {
  routeGet([job])
  renderWithRouter(<ContentSchedulePage />)

  expect(await screen.findByText('SNS Growth · SNS 投稿')).toBeInTheDocument()
  expect(screen.getByText('朝活')).toBeInTheDocument()
  expect(screen.getByText('停止中')).toBeInTheDocument()
})

it('shows PID nowhere (deleted per audit)', async () => {
  routeGet([job], runningDaemon)
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('PDCA 稼働中')
  expect(screen.queryByText(/PID/)).not.toBeInTheDocument()
})

it('shows cycle count with interval when daemon is running', async () => {
  routeGet([job], runningDaemon)
  renderWithRouter(<ContentSchedulePage />)

  // "サイクル 3（10分ごと）" のように間隔が可視化される
  expect(await screen.findByText(/サイクル 3/)).toBeInTheDocument()
  expect(screen.getByText(/10分ごと/)).toBeInTheDocument()
})

// ---- エラー表示 --------------------------------------------------------------

it('shows error state with retry when API fails', async () => {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') throw new Error('接続エラー')
    if (method === 'GET' && path === '/api/organizations') return []
    if (method === 'GET' && path === '/api/content-daemon/status') throw new Error('デーモン取得失敗')
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    throw new Error(`Unexpected ${method} ${path}`)
  })
  renderWithRouter(<ContentSchedulePage />)

  // エラー状態と再試行ボタンが表示される
  expect(await screen.findByText('データの読み込みに失敗しました')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
})

// ---- 失敗詳細表示 ------------------------------------------------------------

it('shows last_detail when job has error status', async () => {
  routeGet([failedJob])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('SNS Growth · SNS 投稿')
  expect(screen.getByText(/Claude rate-limited during generation/)).toBeInTheDocument()
  expect(screen.getByText(/失敗原因/)).toBeInTheDocument()
})

it('does not show failure detail section when job succeeded', async () => {
  const successJob = { ...job, last_status: 'success', last_detail: '' }
  routeGet([successJob])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('SNS Growth · SNS 投稿')
  expect(screen.queryByText(/失敗原因/)).not.toBeInTheDocument()
})

// ---- status ラベル日本語化 ---------------------------------------------------

it('displays last_status as Japanese label not raw English', async () => {
  const errorJob = { ...job, last_status: 'error' }
  routeGet([errorJob])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('SNS Growth · SNS 投稿')
  // 日本語化: 'error' → 'エラー'
  expect(screen.getByText('エラー')).toBeInTheDocument()
  // 生値は表示されない
  expect(screen.queryByText(/\(error\)/)).not.toBeInTheDocument()
})

// ---- ジョブ作成 --------------------------------------------------------------

it('creates a content job from the form', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('ジョブがありません')

  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('対象ワークスペース（組織）'), 'SNS Growth')
  await user.type(screen.getByLabelText(/テーマ/), '夜の習慣')
  await user.click(screen.getByRole('button', { name: 'ジョブを追加' }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/content-jobs', {
      org_name: 'SNS Growth',
      kind: 'content_brief',
      theme: '夜の習慣',
      interval_seconds: 86400,
      publish_platform: '',
      publish_mode: 'assisted',
    })
  })
  expect(mockedToast.success).toHaveBeenCalledWith('コンテンツジョブを作成しました。')
})

it('disables the submit button when no org is selected', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('ジョブがありません')
  const submitBtn = screen.getByRole('button', { name: 'ジョブを追加' })
  expect(submitBtn).toBeDisabled()
})

// ---- repo 連携なし時の空状態 -------------------------------------------------

describe('when no repo-bound orgs exist', () => {
  beforeEach(() => {
    mockApi.mockImplementation(async (method: string, path: string) => {
      if (method === 'GET' && path === '/api/content-jobs') return []
      if (method === 'GET' && path === '/api/organizations')
        return [{ name: 'No Repo Org', target_repo_path: null }]
      if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
      if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
      throw new Error(`Unexpected ${method} ${path}`)
    })
  })

  it('shows the empty guidance with org navigation link', async () => {
    renderWithRouter(<ContentSchedulePage />)

    expect(await screen.findByText('連携済みワークスペースがありません')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '組織画面へ' })).toBeInTheDocument()
    // フォームは表示されない
    expect(screen.queryByLabelText('対象ワークスペース（組織）')).not.toBeInTheDocument()
  })
})

// ---- ループ間隔の可変化 ------------------------------------------------------

it('sends the selected daemon interval when starting the loop', async () => {
  routeGet([])
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return []
    if (method === 'GET' && path === '/api/organizations') return []
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'POST' && path === '/api/content-daemon/start') return {}
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('停止中')

  const user = userEvent.setup()
  // 30分に変更
  await user.selectOptions(screen.getByLabelText('巡回間隔'), '1800')
  await user.click(screen.getByRole('button', { name: 'ループ開始' }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/content-daemon/start', { interval: 1800 })
  })
})

it('defaults to 600s (10分) interval for loop start', async () => {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return []
    if (method === 'GET' && path === '/api/organizations') return []
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'POST' && path === '/api/content-daemon/start') return {}
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('停止中')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'ループ開始' }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/content-daemon/start', { interval: 600 })
  })
})

// ---- 今すぐ生成: 連打防止 ----------------------------------------------------

it('disables run-now button while a job is generating', async () => {
  let resolve!: (v: { ok: boolean; detail: string }) => void
  const runPromise = new Promise<{ ok: boolean; detail: string }>((res) => {
    resolve = res
  })

  routeGet([job])
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return [job]
    if (method === 'GET' && path === '/api/organizations')
      return [{ name: 'SNS Growth', target_repo_path: '/repo/sns' }]
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'POST' && path === `/api/content-jobs/${job.job_id}/run`) return runPromise
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('SNS Growth · SNS 投稿')

  const user = userEvent.setup()
  const runBtn = screen.getByRole('button', { name: '今すぐ生成' })
  await user.click(runBtn)

  // 生成中はボタンが無効化される
  expect(screen.getByRole('button', { name: '生成中…' })).toBeDisabled()

  // 完了させる
  resolve({ ok: true, detail: '下書きを生成しました' })
  await waitFor(() => {
    expect(mockedToast.success).toHaveBeenCalledWith('生成しました: 下書きを生成しました')
  })
})

// ---- 削除確認ダイアログ (P0) -------------------------------------------------

it('shows a confirmation dialog before deleting a job', async () => {
  routeGet([job])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('SNS Growth · SNS 投稿')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /削除/ }))

  // ダイアログが開く
  expect(screen.getByRole('alertdialog', { hidden: true }) ?? screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('このジョブを削除しますか？')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '削除する' })).toBeInTheDocument()
})

it('cancelling the delete dialog does not call DELETE', async () => {
  routeGet([job])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('SNS Growth · SNS 投稿')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /削除/ }))
  expect(screen.getByText('このジョブを削除しますか？')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'キャンセル' }))

  expect(mockApi).not.toHaveBeenCalledWith('DELETE', expect.stringContaining('/api/content-jobs/'))
})

it('confirming the delete dialog calls DELETE and shows success toast', async () => {
  routeGet([job])
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return [job]
    if (method === 'GET' && path === '/api/organizations')
      return [{ name: 'SNS Growth', target_repo_path: '/repo/sns' }]
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'DELETE' && path === `/api/content-jobs/${job.job_id}`) return {}
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('SNS Growth · SNS 投稿')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /削除/ }))
  await user.click(screen.getByRole('button', { name: '削除する' }))

  await waitFor(() => {
    expect(mockApi).toHaveBeenCalledWith('DELETE', `/api/content-jobs/${job.job_id}`)
  })
  expect(mockedToast.success).toHaveBeenCalledWith('ジョブを削除しました。')
})

// ---- トグル: 成功フィードバック ----------------------------------------------

it('shows success toast when toggling a job', async () => {
  routeGet([job])
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return [job]
    if (method === 'GET' && path === '/api/organizations')
      return [{ name: 'SNS Growth', target_repo_path: '/repo/sns' }]
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs')) return []
    if (method === 'PATCH' && path === `/api/content-jobs/${job.job_id}`) return {}
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('SNS Growth · SNS 投稿')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '無効化' }))

  await waitFor(() => {
    expect(mockedToast.success).toHaveBeenCalledWith('ジョブを無効化しました。')
  })
})

// ---- サイクルログ ------------------------------------------------------------

it('renders cycle logs with legend', async () => {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return []
    if (method === 'GET' && path === '/api/organizations') return []
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
    if (method === 'GET' && path.startsWith('/api/content-daemon/logs'))
      return [
        { cycle: 1, completed_at: '2026-06-14T10:00:00Z', due_jobs: 3, generated: 2, interventions: 0 },
        { cycle: 2, completed_at: '2026-06-14T10:10:00Z', due_jobs: 1, generated: 0, interventions: 1 },
      ]
    throw new Error(`Unexpected ${method} ${path}`)
  })

  renderWithRouter(<ContentSchedulePage />)

  expect(await screen.findByText('最近のサイクル')).toBeInTheDocument()
  // 凡例
  expect(screen.getByText(/対象\(due\) \/ 生成 \/ 介入\(human\)/)).toBeInTheDocument()
  // サイクル行 (表示は reversed なので #2 が先)
  expect(screen.getByText(/#2/)).toBeInTheDocument()
  expect(screen.getByText(/#1/)).toBeInTheDocument()
})

// ---- 種類の説明 --------------------------------------------------------------

it('shows kind description when kind is selected', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)

  // content_brief がデフォルト
  expect(await screen.findByText('短文の SNS 投稿ドラフトを定期生成します。')).toBeInTheDocument()
})

// ---- テーマの任意表示 --------------------------------------------------------

it('shows that theme is optional in the label', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('ジョブがありません')
  expect(screen.getByText(/任意・未指定なら組織のデフォルト方針で生成/)).toBeInTheDocument()
})
