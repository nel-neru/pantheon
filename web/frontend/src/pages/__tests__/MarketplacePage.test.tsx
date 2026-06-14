import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

it('「この会社を作成」は確認ダイアログを開き、確認後に install API を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  // クリックして確認ダイアログを開く
  fireEvent.click(await screen.findByRole('button', { name: 'この会社を作成' }))

  // ConfirmDialog が表示されていることを確認
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/note 販売会社/)).toBeInTheDocument()

  // 確認ボタンをクリック（ConfirmDialogのconfirmLabel='この会社を作成'）
  fireEvent.click(within(dialog).getByRole('button', { name: 'この会社を作成' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/company-plugins/note_sales/install', {})
  )
})

it('「この会社を作成」でキャンセルすると install API を呼ばない', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  fireEvent.click(await screen.findByRole('button', { name: 'この会社を作成' }))

  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'キャンセル' }))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(mockApi).not.toHaveBeenCalledWith('POST', expect.stringContaining('/install'), expect.anything())
})

it('新規会社候補（トレンド発）を一覧表示する', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('新規会社候補（トレンド発・要承認）')).toBeInTheDocument()
  expect(screen.getByText('[新規会社候補] ai 事業')).toBeInTheDocument()
})

it('新規会社候補に「承認インボックスで開く」リンクを表示する', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('[新規会社候補] ai 事業')
  expect(screen.getByRole('button', { name: /承認インボックスで開く/ })).toBeInTheDocument()
})

it('優先度バッジが日本語ラベルで表示される (high → 高)', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('[新規会社候補] ai 事業')
  // priority 'high' → priorityLabel → '高'
  expect(screen.getByText('高')).toBeInTheDocument()
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

it('事業部「追加」は確認ダイアログを開き、確認後に POST を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('X集客事業部')
  const addButtons = screen.getAllByRole('button', { name: '追加' })
  fireEvent.click(addButtons[0])

  // ConfirmDialog が開く
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/X集客事業部/)).toBeInTheDocument()
  // 「My Co」はタイトルと説明両方に現れるため getAllByText で確認
  expect(within(dialog).getAllByText(/My Co/).length).toBeGreaterThan(0)

  // 確認ボタンをクリック
  fireEvent.click(within(dialog).getByRole('button', { name: '追加する' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/organizations/My%20Co/divisions', {
      plugin_id: 'x_audience',
    })
  )
})

it('事業部「追加」でキャンセルすると divisions API を呼ばない', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('X集客事業部')
  const addButtons = screen.getAllByRole('button', { name: '追加' })
  fireEvent.click(addButtons[0])

  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'キャンセル' }))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(mockApi).not.toHaveBeenCalledWith('POST', expect.stringContaining('/divisions'), expect.anything())
})

it('事業部追加成功後にデータ再取得(load)を呼ぶ', async () => {
  wireApi()
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('X集客事業部')
  const addButtons = screen.getAllByRole('button', { name: '追加' })
  fireEvent.click(addButtons[0])

  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: '追加する' }))

  // divisions POST の後に company-plugin-manifests が再取得される(load呼び出しの証拠)
  await waitFor(() => {
    const getAllCalls = mockApi.mock.calls
    const divisionCall = getAllCalls.some(
      ([m, p]) => m === 'POST' && (p as string).includes('/divisions')
    )
    const reloadCall = getAllCalls.filter(
      ([m, p]) => m === 'GET' && p === '/api/company-plugin-manifests'
    )
    // 初回load + 追加後のload = 少なくとも2回
    expect(divisionCall).toBe(true)
    expect(reloadCall.length).toBeGreaterThanOrEqual(2)
  })
})

it('組織が0件のとき「会社プラグインから作成してください」の案内を表示する', async () => {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests') return Promise.resolve(companyManifests)
    if (path === '/api/division-plugins') return Promise.resolve(divisionPlugins)
    if (path === '/api/organizations') return Promise.resolve([])
    if (path === '/api/hq/business-proposals') return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('X集客事業部')
  expect(
    screen.getByText(/先に上の「会社プラグイン」からOrganizationを作成してください/)
  ).toBeInTheDocument()
})

it('manifests が空のとき空状態テキストを表示する', async () => {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests') return Promise.resolve({ manifests: [] })
    if (path === '/api/division-plugins') return Promise.resolve(divisionPlugins)
    if (path === '/api/organizations') return Promise.resolve(orgs)
    if (path === '/api/hq/business-proposals') return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('会社プラグインがありません。')).toBeInTheDocument()
})

it('division が空のとき空状態テキストを表示する', async () => {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests') return Promise.resolve(companyManifests)
    if (path === '/api/division-plugins') return Promise.resolve({ plugins: [] })
    if (path === '/api/organizations') return Promise.resolve(orgs)
    if (path === '/api/hq/business-proposals') return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('事業部プラグインがありません。')).toBeInTheDocument()
})

it('API エラー時に再試行ボタンを表示する', async () => {
  mockApi.mockRejectedValue(new Error('接続失敗'))
  renderWithRouter(<MarketplacePage />)

  expect(await screen.findByText('読み込みに失敗しました')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
})

it('KPI が空の場合は「—」を表示する', async () => {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests')
      return Promise.resolve({
        manifests: [
          {
            id: 'no_kpi',
            label: 'KPIなし会社',
            divisions: ['事業部A'],
            initial_kpis: [],
          },
        ],
      })
    if (path === '/api/division-plugins') return Promise.resolve({ plugins: [] })
    if (path === '/api/organizations') return Promise.resolve(orgs)
    if (path === '/api/hq/business-proposals') return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })
  renderWithRouter(<MarketplacePage />)

  await screen.findByText('KPIなし会社')
  // initial_kpis が空 → '—' プレースホルダ
  const cells = screen.getAllByText('—')
  expect(cells.length).toBeGreaterThan(0)
})
