import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, it, vi } from 'vitest'

import { ConfirmDialog } from '../ConfirmDialog'

function Harness({
  confirmWord,
  onConfirm,
}: {
  confirmWord?: string
  onConfirm: () => void | Promise<void>
}) {
  const [open, setOpen] = useState(true)
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={setOpen}
      title="本当に実行しますか？"
      description="この操作は取り消せません。"
      confirmLabel="実行する"
      confirmWord={confirmWord}
      onConfirm={onConfirm}
    />
  )
}

it('確認ボタンで onConfirm を呼び、キャンセルでは呼ばない', async () => {
  const onConfirm = vi.fn()
  render(<Harness onConfirm={onConfirm} />)

  expect(screen.getByText('本当に実行しますか？')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '実行する' }))
  expect(onConfirm).toHaveBeenCalledTimes(1)
})

it('名前一致モードでは一致するまで確認ボタンが無効', async () => {
  const onConfirm = vi.fn()
  render(<Harness confirmWord="DELETE" onConfirm={onConfirm} />)

  const confirmBtn = screen.getByRole('button', { name: '実行する' })
  expect(confirmBtn).toBeDisabled()

  await userEvent.type(screen.getByLabelText('確認文字列'), 'DELETE')
  expect(confirmBtn).toBeEnabled()
  await userEvent.click(confirmBtn)
  expect(onConfirm).toHaveBeenCalledTimes(1)
})
