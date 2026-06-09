import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HelpPage } from '../HelpPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

describe('HelpPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
    mockStreamSSE.mockReset()
  })

  it('renders the help header and default overview tab', () => {
    renderWithRouter(<HelpPage />)

    expect(screen.getByText('ヘルプ')).toBeInTheDocument()
    expect(screen.getByText('概要')).toBeInTheDocument()
    expect(screen.getByText('Pantheon とは')).toBeInTheDocument()
    expect(screen.getByText(/AI組織が自律的に計画・実行・改善を担うプラットフォーム/)).toBeInTheDocument()
    expect(screen.getByText('一人でも、組織で動く。')).toBeInTheDocument()
  })

  it('shows data management and settings guidance in the page usage tab', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    await user.click(screen.getByRole('button', { name: 'データ管理' }))

    expect(screen.getByText('ゴール履歴')).toBeInTheDocument()
    expect(screen.getByText(/knowledge 配下のファイルを一覧表示し、クリックでプレビューできます/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '設定' }))

    // 実データのみ: マルチプロバイダ/API キーの記述は廃止し、claude CLI 前提に統一
    expect(screen.getByText(/ローカルの claude CLI を使用します（API キー不要）/)).toBeInTheDocument()
    expect(screen.getByText(/Opus \/ Sonnet \/ Haiku/)).toBeInTheDocument()
  })

  it('documents the supported slash commands with /goal', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))

    expect(await screen.findByText('/goal')).toBeInTheDocument()
    expect(screen.queryByText('/goals')).not.toBeInTheDocument()
  })

  it('switches to the advanced settings tab', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '設定・CLI・トラブル' }))

    // 既定で開くのは「起動とインストール」節（exe 起動の案内）
    expect(screen.getByText('起動とインストール')).toBeInTheDocument()
    expect(screen.getByText(/exe をダブルクリックすれば GUI が起動し/)).toBeInTheDocument()

    // 実行ランタイム節は折りたたまれているので、展開してから内容を検証する
    await user.click(screen.getByRole('button', { name: '実行ランタイム（claude CLI）' }))
    expect(screen.getByText(/ホスト型 LLM の API キーは使いません/)).toBeInTheDocument()
  })

  it('collapses and expands accordion sections', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    const trigger = screen.getByRole('button', { name: 'Pantheon とは' })
    expect(screen.getByText('一人でも、組織で動く。')).toBeInTheDocument()

    await user.click(trigger)
    expect(screen.queryByText('一人でも、組織で動く。')).not.toBeInTheDocument()

    await user.click(trigger)
    expect(screen.getByText('一人でも、組織で動く。')).toBeInTheDocument()
  })
})
