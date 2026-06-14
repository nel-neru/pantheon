import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ErrorBoundary } from '../ErrorBoundary'

function Boom(): never {
  throw new Error('意図的な失敗')
}

beforeEach(() => {
  // 例外時の componentDidCatch / React のエラーログを抑制
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

it('子が例外を投げるとフォールバックを表示する', () => {
  render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  )
  expect(screen.getByRole('alert')).toBeInTheDocument()
  expect(screen.getByText('画面の表示中に問題が発生しました')).toBeInTheDocument()
  expect(screen.getByText('意図的な失敗')).toBeInTheDocument()
})

it('正常な子はそのまま描画する', () => {
  render(
    <ErrorBoundary>
      <div>正常な内容</div>
    </ErrorBoundary>,
  )
  expect(screen.getByText('正常な内容')).toBeInTheDocument()
})
