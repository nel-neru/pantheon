import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import { Observatory } from '../Observatory'
import { Pantheon } from '../Pantheon'
import { Atelier } from '../Atelier'
import { Signals } from '../Signals'
import { Inbox } from '../Inbox'

// 全ページは展示ヘッダー（kicker）を同期描画する。ネットワークは空配列を返す。
beforeEach(() => {
  globalThis.fetch = vi.fn(async () => ({
    ok: true,
    json: async () => [],
  })) as unknown as typeof fetch
})

describe('Atelier pages render their exhibition header', () => {
  it('Observatory', () => {
    render(<Observatory />)
    expect(screen.getByText('The Observatory')).toBeInTheDocument()
  })

  it('Pantheon', () => {
    render(<Pantheon />)
    expect(screen.getByText('The Pantheon')).toBeInTheDocument()
  })

  it('Atelier', () => {
    render(<Atelier />)
    expect(screen.getByText('The Atelier')).toBeInTheDocument()
  })

  it('Signals', () => {
    render(<Signals />)
    expect(screen.getByText('The Signals')).toBeInTheDocument()
  })

  it('Inbox', () => {
    render(<Inbox />)
    expect(screen.getByText('The Review Desk')).toBeInTheDocument()
  })
})
