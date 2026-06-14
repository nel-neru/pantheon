import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { OnboardingPage } from '../OnboardingPage'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

beforeEach(() => {
  mockApi.mockReset()
})

const manifests = {
  manifests: [
    {
      id: 'note_sales',
      label: 'note 販売会社',
      genre: 'digital_content',
      description: 'note で販売',
      divisions: ['コンテンツ企画部', '販売部'],
      initial_kpis: ['売上'],
    },
  ],
}

function wireApi() {
  mockApi.mockImplementation((method: string, path: string) => {
    if (path === '/api/company-plugin-manifests') return Promise.resolve(manifests)
    if (method === 'POST' && path.includes('/install')) {
      return Promise.resolve({ org_name: 'note 販売会社', divisions: ['コンテンツ企画部'] })
    }
    return Promise.resolve({})
  })
}

describe('ステップ遷移', () => {
  it('イントロから始めるとテンプレ一覧が表示される', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    expect(screen.getByText('副業ポートフォリオを自動構築')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    expect(await screen.findByText('note 販売会社')).toBeInTheDocument()
  })

  it('ステップインジケータが現在のステップを表示する', () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    expect(screen.getByText(/ステップ 1 \/ 3/)).toBeInTheDocument()
    expect(screen.getByText(/はじめに/)).toBeInTheDocument()
  })

  it('ステップ2でステップインジケータが更新される', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    await screen.findByText('note 販売会社')
    expect(screen.getByText(/ステップ 2 \/ 3/)).toBeInTheDocument()
    expect(screen.getByText(/テンプレを選ぶ/)).toBeInTheDocument()
  })
})

describe('テンプレート一覧', () => {
  it('initial_kpis 列が表示される', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    await screen.findByText('note 販売会社')
    expect(screen.getByText('初期KPI')).toBeInTheDocument()
    expect(screen.getByText('売上')).toBeInTheDocument()
  })

  it('initial_kpis がない場合は「—」を表示する', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/company-plugin-manifests') {
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
      }
      return Promise.resolve({})
    })
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    await screen.findByText('KPIなし会社')
    // empty kpi → dash
    const cells = screen.getAllByText('—')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('テンプレートが空の場合は empty-state を表示する', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/company-plugin-manifests') {
        return Promise.resolve({ manifests: [] })
      }
      return Promise.resolve({})
    })
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    expect(await screen.findByText('テンプレートがありません')).toBeInTheDocument()
  })
})

describe('ロードエラー', () => {
  it('読み込み失敗時にエラーと再試行ボタンを表示する', async () => {
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/company-plugin-manifests') {
        return Promise.reject(new Error('サーバーエラー'))
      }
      return Promise.resolve({})
    })
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    expect(await screen.findByText('テンプレートの読み込みに失敗しました')).toBeInTheDocument()
    expect(screen.getByText('サーバーエラー')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument()
  })

  it('再試行ボタンで API を再度叩く', async () => {
    let callCount = 0
    mockApi.mockImplementation((method: string, path: string) => {
      if (path === '/api/company-plugin-manifests') {
        callCount++
        if (callCount === 1) return Promise.reject(new Error('最初の失敗'))
        return Promise.resolve(manifests)
      }
      return Promise.resolve({})
    })
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))

    await screen.findByText('テンプレートの読み込みに失敗しました')
    fireEvent.click(screen.getByRole('button', { name: '再試行' }))

    expect(await screen.findByText('note 販売会社')).toBeInTheDocument()
  })
})

describe('作成確認ダイアログ（安全ゲート）', () => {
  it('「作成」クリックで確認ダイアログが開き、API はまだ呼ばれない', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    // reset call count after load
    mockApi.mockClear()
    wireApi()

    fireEvent.click(screen.getByRole('button', { name: '作成' }))

    // dialog should open
    expect(await screen.findByText(/「note 販売会社」を起動しますか？/)).toBeInTheDocument()
    // install API not called yet
    expect(mockApi).not.toHaveBeenCalledWith('POST', expect.stringContaining('/install'), expect.anything())
  })

  it('ダイアログで「作成する」を確定すると install API を叩き、作成済みに反映される', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    mockApi.mockClear()
    wireApi()

    fireEvent.click(screen.getByRole('button', { name: '作成' }))
    await screen.findByText(/「note 販売会社」を起動しますか？/)

    fireEvent.click(screen.getByRole('button', { name: '作成する' }))

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('POST', '/api/company-plugins/note_sales/install', {})
    )
    expect(await screen.findByText('作成済み（1 社）')).toBeInTheDocument()
  })

  it('ダイアログで「キャンセル」すると API は呼ばれない', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    mockApi.mockClear()
    wireApi()

    fireEvent.click(screen.getByRole('button', { name: '作成' }))
    await screen.findByText(/「note 販売会社」を起動しますか？/)

    fireEvent.click(screen.getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => {
      expect(screen.queryByText(/「note 販売会社」を起動しますか？/)).not.toBeInTheDocument()
    })
    expect(mockApi).not.toHaveBeenCalledWith('POST', expect.stringContaining('/install'), expect.anything())
  })
})

describe('ステップ3 完了画面', () => {
  it('会社を作成後に「完了する」でステップ3に進む', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    fireEvent.click(screen.getByRole('button', { name: '作成' }))
    await screen.findByText(/「note 販売会社」を起動しますか？/)
    fireEvent.click(screen.getByRole('button', { name: '作成する' }))
    await screen.findByText('作成済み（1 社）')

    fireEvent.click(screen.getByRole('button', { name: /完了する/ }))

    expect(await screen.findByText('準備ができました')).toBeInTheDocument()
    expect(screen.getByText(/ステップ 3 \/ 3/)).toBeInTheDocument()
  })

  it('ステップ3にダッシュボード・組織・承認インボックスへのリンクがある', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    fireEvent.click(screen.getByRole('button', { name: '作成' }))
    await screen.findByText(/「note 販売会社」を起動しますか？/)
    fireEvent.click(screen.getByRole('button', { name: '作成する' }))
    await screen.findByText('作成済み（1 社）')

    fireEvent.click(screen.getByRole('button', { name: /完了する/ }))
    await screen.findByText('準備ができました')

    expect(screen.getByRole('link', { name: 'ダッシュボードへ' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '組織を見る' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '承認インボックス' })).toBeInTheDocument()
  })

  it('「完了する」は会社を作成しないと無効', async () => {
    wireApi()
    renderWithRouter(<OnboardingPage />)

    fireEvent.click(screen.getByRole('button', { name: /始める/ }))
    await screen.findByText('note 販売会社')

    const completeBtn = screen.getByRole('button', { name: /完了する/ })
    expect(completeBtn).toBeDisabled()
  })
})
