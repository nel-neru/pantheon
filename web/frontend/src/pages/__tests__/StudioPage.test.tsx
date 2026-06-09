import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'

import { StudioPage } from '../StudioPage'
import { renderWithRouter } from '@/test/utils'

it('X タブで文字数カウントを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('本文'), 'こんにちは')
  // 5字 / 280
  expect(screen.getByText('5 / 280')).toBeInTheDocument()
})

it('note タブに切り替えるとタイトル入力と記事プレビューが出る', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /note/ }))
  expect(screen.getByLabelText('タイトル')).toBeInTheDocument()
  await user.type(screen.getByLabelText('タイトル'), '朝活のコツ')
  expect(screen.getByRole('heading', { name: '朝活のコツ' })).toBeInTheDocument()
})

it('280字超でスレッド分割プレビューを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  const long = 'あ'.repeat(600)
  // paste で高速入力（type は1文字ずつで遅い）
  await user.click(screen.getByLabelText('本文'))
  await user.paste(long)
  expect(await screen.findByText('ツイート 1')).toBeInTheDocument()
  expect(screen.getByText('ツイート 2')).toBeInTheDocument()
})
