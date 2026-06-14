import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HelpPage, PAGE_SECTION_ROUTES } from '../HelpPage'
import { mockApi, mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// ナビ定数（App.tsx の navGroups から /help ページ自身が担保すべきルートを列挙）
// HelpPage の pageSections がこのリストをカバーしているか drift-detection テストで確認する。
const EXPECTED_NAV_ROUTES = [
  '/dashboard',
  '/orgs',
  '/proposals',
  '/agents',
  '/handoffs',
  '/content',
  '/revenue',
  '/sessions',
  '/board',
  '/data',
  '/settings',
  '/help',
] as const

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

  it('shows subtitle via PageHeader', () => {
    renderWithRouter(<HelpPage />)
    expect(screen.getByText('現在の画面構成に合わせた Pantheon の操作ガイドです。')).toBeInTheDocument()
  })

  it('pages tab shows revenue section', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    // ダッシュボードが先頭で開く
    expect(screen.getByRole('button', { name: 'ダッシュボード' })).toBeInTheDocument()
    // 収益セクションが存在する
    expect(screen.getByRole('button', { name: '収益' })).toBeInTheDocument()
  })

  it('shows revenue section content when expanded', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    await user.click(screen.getByRole('button', { name: '収益' }))

    expect(screen.getByText(/収益の集計・トラッキングを確認します/)).toBeInTheDocument()
    expect(screen.getByText('収益サマリ')).toBeInTheDocument()
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

    await user.click(screen.getByRole('button', { name: '概要' }))
    await user.click(screen.getByRole('button', { name: '対話・実行（wmux 連携・外部）' }))

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

  it('help section does not mention API キー取得先 (fact error fixed)', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    await user.click(screen.getByRole('button', { name: 'ヘルプ' }))

    // 事実誤り文言が存在しないことを確認
    expect(screen.queryByText(/API キー取得先/)).not.toBeInTheDocument()
    // 正しい説明が入っていること
    expect(screen.getByText(/起動とインストール、claude CLI、CLI コマンド、よくある問題/)).toBeInTheDocument()
  })

  it('wmux section is in the overview tab, not in the pages tab as a nav item', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    // 概要タブに wmux セクションがある
    await user.click(screen.getByRole('button', { name: '対話・実行（wmux 連携・外部）' }))
    expect(screen.getByText(/チャットと実行（分析・ゴール・適用）は wmux のタブで行います/)).toBeInTheDocument()

    // 各画面タブに wmux の単独アコーディオンは存在しない（ナビ非存在のため）
    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    // wmux 見出しは pages タブにない（overview に移動済み）
    const pageTabPanel = screen.getByRole('button', { name: 'セッション' })
    expect(pageTabPanel).toBeInTheDocument()
    // 'workspace' は pages リストに無い（wmux の旧セクション id）
    expect(screen.queryByRole('button', { name: '対話・実行（wmux）' })).not.toBeInTheDocument()
  })

  it('sessions and board are separate sections in the pages tab', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))

    expect(screen.getByRole('button', { name: 'セッション' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '作業ボード' })).toBeInTheDocument()
  })

  it('board section content is independent from sessions', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '各画面の使い方' }))
    await user.click(screen.getByRole('button', { name: '作業ボード' }))

    expect(screen.getByText(/Kanban ビュー/)).toBeInTheDocument()
    expect(screen.getByText(/タスク起票/)).toBeInTheDocument()
  })

  it('CodeBlock renders copy button', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    // 「使い始めの流れ」節に CodeBlock が含まれるので展開してコピーボタンを確認する
    await user.click(screen.getByRole('button', { name: '使い始めの流れ' }))
    const copyBtns = screen.getAllByRole('button', { name: /をコピー/ })
    expect(copyBtns.length).toBeGreaterThan(0)
  })

  it('URL CodeBlock renders as an anchor link', async () => {
    const user = userEvent.setup()
    renderWithRouter(<HelpPage />)

    await user.click(screen.getByRole('button', { name: '設定・CLI・トラブル' }))
    // http://localhost:7860 は <a> タグとしてレンダリングされる
    const link = screen.getByRole('link', { name: 'http://localhost:7860' })
    expect(link).toHaveAttribute('href', 'http://localhost:7860')
    expect(link).toHaveAttribute('target', '_blank')
  })

  // ─── ドリフト検出: pageSections と期待ルートの差分 ───────────────────────────
  it('PAGE_SECTION_ROUTES covers all expected nav routes (drift detection)', () => {
    const covered = new Set(PAGE_SECTION_ROUTES)
    const missing = EXPECTED_NAV_ROUTES.filter((r) => !covered.has(r))
    expect(missing, `pageSections にカバーされていないナビルート: ${missing.join(', ')}`).toHaveLength(0)
  })

  it('PAGE_SECTION_ROUTES has no extra routes not in expected nav (drift detection)', () => {
    const expected = new Set(EXPECTED_NAV_ROUTES)
    const extra = PAGE_SECTION_ROUTES.filter((r) => !expected.has(r))
    expect(extra, `PAGE_SECTION_ROUTES に期待外のルート: ${extra.join(', ')}`).toHaveLength(0)
  })
})
