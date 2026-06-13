import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

import { MarketplacePage } from '../MarketplacePage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const companyManifests = {
  manifests: [
    {
      id: 'note_sales',
      label: 'note 販売会社',
      genre: 'digital_content',
      description: 'note で販売',
      divisions: ['コンテンツ企画部', '販売・マーケティング部'],
      initial_kpis: ['有料記事の売上'],
    },
  ],
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
const businessProposals = {
  items: [
    {
      id: 'b1',
      org_name: 'My Co',
      title: '[新規会社候補] ai 事業',
      priority: 'high',
      expected_impact: '新収益モデル会社の立ち上げ候補',
      route: '/proposals?org=My%20Co',
    },
  ],
  count: 1,
}

function wireApi() {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests') return Promise.resolve(companyManifests)
    if (path === '/api/division-plugins') return Promise.resolve(divisionPlugins)
    if (path === '/api/organizations') return Promise.resolve(orgs)
    if (path === '/api/hq/business-proposals') return Promise.resolve(businessProposals)
    if (method === 'POST' && path === '/api/hq/business-proposals/scan') {
      return Promise.resolve({ proposals: 1 })
    }
    if (method === 'POST' && path === '/api/hq/untapped-genres/scan') {
      return Promise.resolve({ proposals: 1 })
    }
    if (method === 'POST' && path.includes('/install')) {
      return Promise.resolve({ org_name: 'note 販売会社', divisions: ['コンテンツ企画部'] })
    }
    if (method === 'POST' && path.includes('/divisions')) {
      return Promise.resolve({ division: { name: 'X集客事業部' } })
    }
    return Promise.resolve({})
  })
}

it('会社プラグイン manifest と事業部プラグインを一覧表示する', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  expect(
    await screen.findByText('会社プラグイン（テンプレートから1クリックで会社を起動）')
  ).toBeInTheDocument()
  expect(screen.getByText('事業部プラグイン（既存の会社に追加）')).toBeInTheDocument()
  expect(screen.getByText('note 販売会社')).toBeInTheDocument()
  expect(screen.getByText('X集客事業部')).toBeInTheDocument()
})

it('「この会社を作成」で install API を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  fireEvent.click(await screen.findByRole('button', { name: 'この会社を作成' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/company-plugins/note_sales/install', {})
  )
})

it('新規会社候補（トレンド発）を一覧表示する', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('新規会社候補（トレンド発・要承認）')).toBeInTheDocument()
  expect(screen.getByText('[新規会社候補] ai 事業')).toBeInTheDocument()
})

it('「トレンドからスキャン」で scan API を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  fireEvent.click(await screen.findByRole('button', { name: 'トレンドからスキャン' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/hq/business-proposals/scan', {
      min_score: 7.0,
    })
  )
})

it('「未開拓ジャンルをスキャン」で untapped scan API を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  fireEvent.click(await screen.findByRole('button', { name: '未開拓ジャンルをスキャン' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/hq/untapped-genres/scan', { min_score: 7.0 })
  )
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
