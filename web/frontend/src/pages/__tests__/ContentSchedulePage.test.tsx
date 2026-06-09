import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
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

const stoppedDaemon = {
  running: false,
  pid: null,
  rate_limited: false,
  retry_at: null,
  cycle_count: 0,
  interval_seconds: null,
}

function routeGet(jobs: typeof job[]) {
  mockApi.mockImplementation(async (method: string, path: string) => {
    if (method === 'GET' && path === '/api/content-jobs') return jobs
    if (method === 'GET' && path === '/api/organizations')
      return [{ name: 'SNS Growth', target_repo_path: '/repo/sns' }]
    if (method === 'GET' && path === '/api/content-daemon/status') return stoppedDaemon
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

it('lists content jobs and shows the stopped PDCA badge', async () => {
  routeGet([job])
  renderWithRouter(<ContentSchedulePage />)

  expect(await screen.findByText('SNS Growth · SNS 投稿')).toBeInTheDocument()
  expect(screen.getByText('朝活')).toBeInTheDocument()
  expect(screen.getByText('停止中')).toBeInTheDocument()
})

it('creates a content job from the form', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)

  await screen.findByText('ジョブがありません')

  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('対象ワークスペース（組織）'), 'SNS Growth')
  await user.type(screen.getByLabelText('テーマ'), '夜の習慣')
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

it('requires selecting a workspace before creating', async () => {
  routeGet([])
  renderWithRouter(<ContentSchedulePage />)
  await screen.findByText('ジョブがありません')

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'ジョブを追加' }))
  expect(mockedToast.error).toHaveBeenCalledWith('対象ワークスペース（組織）を選んでください。')
})
