import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { MarketplacePage } from '../MarketplacePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const companyPlugins = {
  plugins: [{ id: 'sns_growth', label: 'sns_growth', division_count: 2, divisions: ['A部', 'B部'] }],
}
const divisionPlugins = {
  plugins: [
    { id: 'x_audience', label: 'X集客事業部', category: 'audience', description: 'X で集客' },
    {
      id: 'note_monetization',
      label: 'note販売事業部',
      category: 'monetization',
      description: 'note で収益化',
    },
  ],
}
const orgs = [{ id: '1', name: 'My Co' }]

function wireApi() {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugins') return Promise.resolve(companyPlugins)
    if (path === '/api/division-plugins') return Promise.resolve(divisionPlugins)
    if (path === '/api/organizations') return Promise.resolve(orgs)
    if (method === 'POST' && path.includes('/divisions')) {
      return Promise.resolve({ division: { name: 'X集客事業部' } })
    }
    return Promise.resolve({})
  })
}

it('会社プラグインと事業部プラグインを一覧表示する', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('会社プラグイン（新しい収益モデル会社）')).toBeInTheDocument()
  expect(screen.getByText('事業部プラグイン（既存の会社に追加）')).toBeInTheDocument()
  expect(screen.getByText('X集客事業部')).toBeInTheDocument()
  expect(screen.getByText('note販売事業部')).toBeInTheDocument()
})

it('事業部プラグインを選択中の組織に追加する POST を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('X集客事業部')
  const addButtons = screen.getAllByRole('button', { name: '追加' })
  fireEvent.click(addButtons[0])

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/organizations/My%20Co/divisions', {
      plugin_id: 'x_audience',
    })
  )
})
