import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, it, vi } from 'vitest'

import { PageHeader } from '../PageHeader'
import { RefreshButton } from '../RefreshButton'
import { ScoreBar } from '../ScoreBar'
import { Tabs } from '../Tabs'

it('PageHeader はタイトル/サブタイトル/アクションを描画', () => {
  render(<PageHeader title="見出し" subtitle="説明" actions={<button type="button">操作</button>} />)
  expect(screen.getByText('見出し')).toBeInTheDocument()
  expect(screen.getByText('説明')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '操作' })).toBeInTheDocument()
})

it('RefreshButton は busy 中は無効化される', () => {
  render(<RefreshButton onClick={() => {}} busy label="更新" />)
  expect(screen.getByRole('button', { name: '更新' })).toBeDisabled()
})

it('ScoreBar は meter ロールと aria 値を持ち 0-100 に丸める', () => {
  render(<ScoreBar score={142} label="健康度" />)
  const meter = screen.getByRole('meter', { name: '健康度' })
  expect(meter).toHaveAttribute('aria-valuenow', '100')
})

it('Tabs は role=tab/aria-selected を持ち選択を切替える', async () => {
  function Harness() {
    const [v, setV] = useState('a')
    return (
      <Tabs
        ariaLabel="フィルタ"
        value={v}
        onChange={setV}
        tabs={[
          { value: 'a', label: 'A', count: 2 },
          { value: 'b', label: 'B' },
        ]}
      />
    )
  }
  render(<Harness />)
  const tabA = screen.getByRole('tab', { name: /A/ })
  expect(tabA).toHaveAttribute('aria-selected', 'true')
  await userEvent.click(screen.getByRole('tab', { name: 'B' }))
  expect(screen.getByRole('tab', { name: 'B' })).toHaveAttribute('aria-selected', 'true')
})

it('Tabs onChange が呼ばれる', async () => {
  const onChange = vi.fn()
  render(
    <Tabs
      value="a"
      onChange={onChange}
      tabs={[
        { value: 'a', label: 'A' },
        { value: 'b', label: 'B' },
      ]}
    />,
  )
  await userEvent.click(screen.getByRole('tab', { name: 'B' }))
  expect(onChange).toHaveBeenCalledWith('b')
})
