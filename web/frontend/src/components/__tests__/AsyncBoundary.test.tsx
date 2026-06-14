import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Inbox } from 'lucide-react'
import { expect, it, vi } from 'vitest'

import { AsyncBoundary } from '../AsyncBoundary'

it('loading 中はスピナーとローディング文言を出す', () => {
  render(
    <AsyncBoundary loading error={null} loadingText="読込中テスト">
      <div>本体</div>
    </AsyncBoundary>,
  )
  expect(screen.getByText('読込中テスト')).toBeInTheDocument()
  expect(screen.queryByText('本体')).not.toBeInTheDocument()
})

it('error のとき再試行ボタンを出し onRetry を呼ぶ', async () => {
  const onRetry = vi.fn()
  render(
    <AsyncBoundary loading={false} error="失敗しました" onRetry={onRetry}>
      <div>本体</div>
    </AsyncBoundary>,
  )
  expect(screen.getByText('失敗しました')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '再試行' }))
  expect(onRetry).toHaveBeenCalledTimes(1)
})

it('isEmpty のとき空状態を出す', () => {
  render(
    <AsyncBoundary
      loading={false}
      error={null}
      isEmpty
      emptyIcon={Inbox}
      emptyTitle="からっぽ"
      emptyHint="まだありません"
    >
      <div>本体</div>
    </AsyncBoundary>,
  )
  expect(screen.getByText('からっぽ')).toBeInTheDocument()
  expect(screen.queryByText('本体')).not.toBeInTheDocument()
})

it('正常時は本体を描画する', () => {
  render(
    <AsyncBoundary loading={false} error={null} isEmpty={false}>
      <div>本体</div>
    </AsyncBoundary>,
  )
  expect(screen.getByText('本体')).toBeInTheDocument()
})
