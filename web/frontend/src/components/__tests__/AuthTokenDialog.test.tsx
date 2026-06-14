import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

import { AuthTokenDialog } from '../AuthTokenDialog'

beforeEach(() => {
  localStorage.clear()
})

it('401 イベントで開き、入力トークンを保存して reload する', async () => {
  const reload = vi.fn()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload },
  })

  render(<AuthTokenDialog />)
  expect(screen.queryByText('APIトークンが必要です')).not.toBeInTheDocument()

  window.dispatchEvent(new Event('pantheon:unauthorized'))
  expect(await screen.findByText('APIトークンが必要です')).toBeInTheDocument()

  await userEvent.type(screen.getByLabelText('APIトークン'), 'secret-token')
  await userEvent.click(screen.getByRole('button', { name: '保存して再読み込み' }))

  expect(localStorage.getItem('pantheon_api_token')).toBe('secret-token')
  expect(reload).toHaveBeenCalled()
})

it('空トークンでは保存ボタンが無効', async () => {
  render(<AuthTokenDialog />)
  window.dispatchEvent(new Event('pantheon:unauthorized'))
  await screen.findByText('APIトークンが必要です')
  expect(screen.getByRole('button', { name: '保存して再読み込み' })).toBeDisabled()
})
