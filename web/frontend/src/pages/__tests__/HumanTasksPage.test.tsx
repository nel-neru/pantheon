import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { HumanTasksPage } from '../HumanTasksPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const tasks = {
  items: [
    {
      task_id: 'human:1',
      title: 'X アカウント作成',
      description: '初回ログインを人間が行う',
      kind: 'account_setup',
      org_name: 'SNS Growth',
      status: 'open',
    },
  ],
  open: 1,
  total: 1,
}

it('未対応の人間タスクを一覧表示する', async () => {
  mockApi.mockResolvedValueOnce(tasks)
  renderWithRouter(<HumanTasksPage />)

  expect(await screen.findByText('X アカウント作成')).toBeInTheDocument()
  expect(screen.getByText('account_setup')).toBeInTheDocument()
})

it('タスクが無いとき空状態を表示する', async () => {
  mockApi.mockResolvedValueOnce({ items: [], open: 0, total: 0 })
  renderWithRouter(<HumanTasksPage />)
  expect(await screen.findByText('未対応の人間タスクはありません')).toBeInTheDocument()
})

it('「完了」で complete API を叩く', async () => {
  mockApi.mockResolvedValueOnce(tasks) // initial GET
  mockApi.mockResolvedValueOnce({ ok: true, status: 'done' }) // complete
  mockApi.mockResolvedValueOnce({ items: [], open: 0, total: 0 }) // reload
  renderWithRouter(<HumanTasksPage />)

  fireEvent.click(await screen.findByRole('button', { name: '完了' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/human-tasks/human%3A1/complete')
  )
})
