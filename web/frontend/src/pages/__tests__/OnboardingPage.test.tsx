import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'

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

it('イントロから始めるとテンプレ一覧が表示される', async () => {
  wireApi()
  renderWithRouter(<OnboardingPage />)

  expect(screen.getByText('副業ポートフォリオを自動構築')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /始める/ }))

  expect(await screen.findByText('note 販売会社')).toBeInTheDocument()
})

it('「作成」で install API を叩き、作成済みに反映される', async () => {
  wireApi()
  renderWithRouter(<OnboardingPage />)

  fireEvent.click(screen.getByRole('button', { name: /始める/ }))
  fireEvent.click(await screen.findByRole('button', { name: '作成' }))

  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith('POST', '/api/company-plugins/note_sales/install', {})
  )
  expect(await screen.findByText('作成済み（1 社）')).toBeInTheDocument()
})
