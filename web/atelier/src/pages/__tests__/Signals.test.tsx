import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import { Signals } from '../Signals'

function trend(score: number) {
  return {
    source: 'web',
    url: 'https://example.com/a',
    title: 'テストの兆し',
    summary: '要約テキスト',
    topics: ['ai'],
    genre: 'ai',
    score,
    raw_excerpt: '',
    collected_at: '2026-06-11T00:00:00Z',
    hash: 'h1',
  }
}

describe('Signals score scaling', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      return {
        ok: true,
        json: async () => (url.includes('/api/trends') ? [trend(7.5)] : []),
      }
    }) as unknown as typeof fetch
  })

  it('maps the backend 0..10 score to a 0..100 index (7.5 → 75)', async () => {
    render(<Signals />)
    // Lead カードの大きな index 数字。0..1 想定の旧実装なら 8 になっていた。
    await waitFor(() => expect(screen.getByText('75')).toBeInTheDocument())
  })
})
