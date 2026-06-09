import { screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import { RevenuePage } from '../RevenuePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const metrics = {
  orgs: [
    { org_name: 'Note Sales', reach: 5000, revenue: 0, posts: 3, reach_but_no_revenue: true },
    { org_name: 'Affiliate Revenue', reach: 2000, revenue: 12000, posts: 5, reach_but_no_revenue: false },
  ],
  total_revenue: 12000,
  total_reach: 7000,
}

it('累計収益とリーチのカードを表示する', async () => {
  mockApi.mockResolvedValueOnce(metrics)
  renderWithRouter(<RevenuePage />)

  expect(await screen.findByText('¥12,000')).toBeInTheDocument()
  expect(screen.getByText('7,000')).toBeInTheDocument()
})

it('「リーチ有・収益0」の組織をアラート表示する', async () => {
  mockApi.mockResolvedValueOnce(metrics)
  renderWithRouter(<RevenuePage />)

  expect(await screen.findByText('リーチはあるが収益0の組織（収益化の余地）')).toBeInTheDocument()
  expect(screen.getAllByText('Note Sales').length).toBeGreaterThan(0)
})

it('成果データが無いとき空状態を表示する', async () => {
  mockApi.mockResolvedValueOnce({ orgs: [], total_revenue: 0, total_reach: 0 })
  renderWithRouter(<RevenuePage />)
  expect(await screen.findByText('成果データがありません')).toBeInTheDocument()
})
