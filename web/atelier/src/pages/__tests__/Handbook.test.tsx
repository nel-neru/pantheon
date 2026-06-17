import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Handbook } from '../Handbook'

describe('Handbook WEB/CLI toggle', () => {
  it('defaults to the WEB flow and switches to the CLI flow on tab click', async () => {
    const user = userEvent.setup()
    render(<Handbook />)

    // 既定は WEB 操作編
    expect(screen.getByText('サーバーを起動してブラウザで開く')).toBeInTheDocument()

    // CLI 操作編に切り替え
    await user.click(screen.getByRole('tab', { name: 'CLI 操作編' }))
    expect(screen.getByText('ジャンル組織を量産する（CLI だけの強み）')).toBeInTheDocument()
  })

  // 回帰ガード: 既知失敗の件数は実基線（chmod 由来の2件）と一致させる。
  // 旧 stale 表記「6件」に戻ると、ユーザーが本物の回帰（旧パス区切り4件分）を
  // 見逃すため、件数のドリフトをここで固定する。
  it('states the current Windows test baseline (2 known failures, not the stale 6)', () => {
    render(<Handbook />)
    expect(screen.queryByText(/既知テスト失敗6件/)).not.toBeInTheDocument()
    expect(screen.getByText(/Windows の既知テスト失敗2件は無視してよい/)).toBeInTheDocument()
  })

  // 回帰ガード: 公開能力の状態を正直に提示する（facade-zero の逆方向＝動く機能を
  // 「未実装」と過小提示しない）。note / X の assisted `_publish_live` は実装済みで
  // 到達可能なので、旧 stale 表記「_publish_live / 投稿 API クライアントは未実装」へ
  // 戻ると、ユーザーは動く収益機能を見落とす。実態（assisted=実装済 / auto=Phase 2）を固定する。
  it('honestly states that note/X assisted publishing is implemented (not the stale "未実装")', () => {
    render(<Handbook />)
    // 旧 stale 表記が復活していないこと。
    expect(screen.queryByText(/投稿 API クライアントは未実装/)).not.toBeInTheDocument()
    // 完全自動だけが Phase 2 という見出しと、assisted の動作説明が出ていること。
    expect(screen.getByText(/完全自動（無人）投稿は現行 main に無い/)).toBeInTheDocument()
    expect(
      screen.getByText(/ブラウザが開いて本文がプリフィルされ、最終の公開ボタンだけ人間が押す/),
    ).toBeInTheDocument()
    // 最重要 Callout（「まず知るべき1点」）も同じ事実を提示し、ページ内で矛盾しないこと
    // （C21: 同じ事実の全 LIVE face を一貫させる）。旧「公開は手動で行います」へ戻ると fail。
    expect(screen.getByText(/公開の最終ボタンは必ず人間が押します/)).toBeInTheDocument()
  })
})
