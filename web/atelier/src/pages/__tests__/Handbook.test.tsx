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
})
