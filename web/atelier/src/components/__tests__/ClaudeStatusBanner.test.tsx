import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { ClaudeStatusBanner } from '../ClaudeStatusBanner'
import { useApi } from '@/hooks/useApi'
import type { PlatformStatus } from '@/lib/types'

const BANNER_HEADING = 'claude CLI が未認証です'

// negative アサート（バナー非表示）を load-bearing にするための positive anchor。
// バナーと同じ /api/platform/status を読み、解決後に確定状態を可視化する。これを
// findByText で待ってからバナー非表示を確認することで、「mount 直後の loading=null」
// ではなく「fetch 解決後の状態」を検証していることを保証する（vacuous-true 回避。
// この anchor 無しだと has_llm:true / error でも常時 null と区別できず実バグを見逃す）。
function ResolutionProbe() {
  const { data, error, loading } = useApi<PlatformStatus>('/api/platform/status')
  const state = loading ? 'loading' : error !== null ? 'error' : `has_llm:${String(data?.has_llm)}`
  return <div data-testid="probe">{state}</div>
}

function renderBanner() {
  return render(
    <MemoryRouter>
      <ClaudeStatusBanner />
    </MemoryRouter>,
  )
}

function renderBannerWithProbe() {
  return render(
    <MemoryRouter>
      <ClaudeStatusBanner />
      <ResolutionProbe />
    </MemoryRouter>,
  )
}

function mockStatus(payload: Record<string, unknown>) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/platform/status')) {
      return { ok: true, json: async () => payload }
    }
    return { ok: true, json: async () => ({}) }
  }) as unknown as typeof fetch
}

// ---- tests -------------------------------------------------------------------

describe('ClaudeStatusBanner', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('(a) has_llm:false → バナー見出しと案内文・リンクが表示される', async () => {
    mockStatus({ has_llm: false, initialized: true })

    renderBanner()

    // バナー見出し（kicker）は解決後にのみ現れる = それ自体が load-bearing な positive anchor
    await waitFor(() => {
      expect(screen.getByText(BANNER_HEADING)).toBeInTheDocument()
    })

    // セットアップ手順リンクが /handbook を指す
    const link = screen.getByRole('link', { name: 'セットアップ手順を見る' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/handbook')
  })

  it('(b) has_llm:true → fetch 解決後もバナーは表示されない（loading の素通りではない）', async () => {
    mockStatus({ has_llm: true, initialized: true })

    renderBannerWithProbe()

    // probe が解決状態を可視化するまで待つ = この時点で fetch は解決・commit 済み。
    // has_llm:true で誤ってバナーを出す回帰（has_llm の値チェック欠落）を捕捉できる。
    await screen.findByText('has_llm:true')

    expect(screen.queryByText(BANNER_HEADING)).not.toBeInTheDocument()
  })

  it('(c) fetch が reject/エラー → fail-safe でバナーは表示されない（誤警告しない）', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.reject(new Error('network error')),
    ) as unknown as typeof fetch

    renderBannerWithProbe()

    // probe が error 状態に遷移するまで待つ = エラーが反映された後で非表示を確認する。
    // error を「未認証」と誤解釈してバナーを出す回帰を捕捉できる。
    await screen.findByText('error')

    expect(screen.queryByText(BANNER_HEADING)).not.toBeInTheDocument()
  })
})
