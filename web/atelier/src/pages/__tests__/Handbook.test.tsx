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
})
