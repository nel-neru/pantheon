import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { NotificationsPage } from '../NotificationsPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const settings = { min_level: 'info', quiet_hours_start: 0, quiet_hours_end: 0 }
const list = {
  items: [
    {
      id: 'n1',
      level: 'warn',
      message: 'health score dropped',
      org_name: 'Co',
      created_at: '2026-06-14T00:00:00+00:00',
      read: false,
    },
  ],
  unread: 1,
}

function wireApi() {
  mockApi.mockImplementation((method: string, path: string) => {
    if (method === 'GET' && path === '/api/notifications') return Promise.resolve(list)
    if (method === 'GET' && path === '/api/notifications/settings') return Promise.resolve(settings)
    if (method === 'POST' && path === '/api/notifications/read-all')
      return Promise.resolve({ marked: 1, unread: 0 })
    if (method === 'POST' && path.endsWith('/read')) return Promise.resolve({ ok: true, unread: 0 })
    if (method === 'PUT' && path === '/api/notifications/settings')
      return Promise.resolve({ ...settings, min_level: 'warn' })
    return Promise.resolve({})
  })
}

it('通知一覧と未読数・設定を表示する', async () => {
  wireApi()
  renderWithRouter(<NotificationsPage />)

  expect(await screen.findByText('health score dropped')).toBeInTheDocument()
  expect(screen.getByText('未読 1 件 / 全 1 件')).toBeInTheDocument()
  expect(screen.getByText('通知設定（時間帯・最小レベル）')).toBeInTheDocument()
})

it('「すべて既読」で read-all API を叩く', async () => {
  wireApi()
  renderWithRouter(<NotificationsPage />)

  await screen.findByText('health score dropped')
  fireEvent.click(screen.getByRole('button', { name: 'すべて既読' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/notifications/read-all')
  )
})

it('最小レベル変更で設定 PUT を叩く', async () => {
  wireApi()
  renderWithRouter(<NotificationsPage />)

  await screen.findByText('health score dropped')
  fireEvent.change(screen.getByDisplayValue('info'), { target: { value: 'warn' } })

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('PUT', '/api/notifications/settings', { min_level: 'warn' })
  )
})
