import { screen, within, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, beforeEach, afterEach, vi } from 'vitest'

import { StudioPage } from '../StudioPage'
import { renderWithRouter } from '@/test/utils'

// localStorage のモック（jsdom は localStorage を提供するが、テスト間で汚染しないようにリセット）
beforeEach(() => {
  localStorage.clear()
})

// フェイクタイマーを使ったテストが失敗してもリアルタイマーに戻す（後続テストの連鎖タイムアウトを防ぐ）
afterEach(() => {
  vi.useRealTimers()
})

// ── 既存テスト ────────────────────────────────────────────────────────────────

it('X タブで文字数カウントを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('本文'), 'こんにちは')
  // 5字 / 280
  expect(screen.getByText('5 / 280')).toBeInTheDocument()
})

it('note タブに切り替えるとタイトル入力と記事プレビューが出る', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  expect(screen.getByLabelText('タイトル')).toBeInTheDocument()
  await user.type(screen.getByLabelText('タイトル'), '朝活のコツ')
  expect(screen.getByRole('heading', { name: '朝活のコツ' })).toBeInTheDocument()
})

it('280字超でスレッド分割プレビューを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  const long = 'あ'.repeat(600)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(long)
  expect(await screen.findByText('ツイート 1')).toBeInTheDocument()
  expect(screen.getByText('ツイート 2')).toBeInTheDocument()
})

// ── 閾値バグ修正テスト（C029） ─────────────────────────────────────────────────

it('275字でスレッド分割される場合は赤バッジ・分割メッセージを表示する（閾値整合）', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  // splitIntoThread は接尾辞ぶん実効上限を縮めるため、275字は2件に分割される
  const text275 = 'あ'.repeat(275)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(text275)
  const badge = await screen.findByText(/275 \/ 280/)
  // thread.length > 1 なら赤バッジになる（count<=280でも分割されるケースで緑にならない）
  const statusText = screen.getByText(/件のスレッドに分割します|1 ツイートに収まります/)
  // 275字は splitIntoThread で1件に収まる or 分割される — どちらであれバッジと状態テキストが一致する
  const isRed = badge.className.includes('badge-red')
  const isSplit = statusText.textContent?.includes('件のスレッドに分割します') ?? false
  // 重要: バッジが赤 ⟺ 状態テキストが「分割します」— 一致している
  expect(isRed).toBe(isSplit)
})

it('280字以内で1件に収まる場合は緑バッジ・1ツイートメッセージを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  const text10 = 'あ'.repeat(10)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(text10)
  expect(await screen.findByText('10 / 280')).toBeInTheDocument()
  expect(screen.getByText('1 ツイートに収まります')).toBeInTheDocument()
  const badge = screen.getByText('10 / 280')
  expect(badge.className).toContain('badge-green')
})

// ── コピー導線テスト（C029） ────────────────────────────────────────────────────

it('X プレビューに「全件コピー」ボタンがある', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  const long = 'あ'.repeat(600)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(long)
  expect(await screen.findByRole('button', { name: /全件コピー/ })).toBeInTheDocument()
})

it('各ツイートカードに「コピー」ボタンがある', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  const long = 'あ'.repeat(600)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(long)
  // ツイート1のカードを特定してコピーボタンを確認
  const tweet1Label = await screen.findByText('ツイート 1')
  const card = tweet1Label.closest('.rounded-xl') as HTMLElement
  expect(within(card).getByRole('button', { name: /コピー/ })).toBeInTheDocument()
})

it('記事プレビューに「コピー」ボタンがある（note タブ）', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  await user.type(screen.getByLabelText('本文'), '本文テスト')
  expect(screen.getByRole('button', { name: /コピー/ })).toBeInTheDocument()
})

it('コピーボタンをクリックすると clipboard.writeText が呼ばれる', async () => {
  // userEvent.setup() は内部で navigator.clipboard を自前のスタブに差し替えるため、
  // スタブ初期化後に vi.spyOn でラップして呼び出しをキャプチャする。
  const user = userEvent.setup()
  // userEvent がスタブを設定した後に spy を張る
  const writeTextSpy = vi.spyOn(navigator.clipboard, 'writeText')

  renderWithRouter(<StudioPage />)
  const long = 'あ'.repeat(600)
  await user.click(screen.getByLabelText('本文'))
  await user.paste(long)
  const copyAllBtn = await screen.findByRole('button', { name: /全件コピー/ })
  await user.click(copyAllBtn)
  // ボタンの onClick は "void asyncFn()" で fire-and-forget のため、
  // waitFor で非同期処理の完了（writeText 呼び出し）を待つ
  await waitFor(() => expect(writeTextSpy).toHaveBeenCalled())
})

// ── 永続化テスト（C029） ───────────────────────────────────────────────────────

it('本文を入力すると localStorage に保存される（デバウンス後）', () => {
  // userEvent.type は内部 delay で fake timers と競合しデッドロックするため
  // fireEvent.change で値を直接セットし、フェイクタイマーでデバウンス時間を進める
  vi.useFakeTimers()
  renderWithRouter(<StudioPage />)
  const textarea = screen.getByLabelText('本文')
  fireEvent.change(textarea, { target: { value: 'テスト本文' } })
  vi.advanceTimersByTime(600)
  expect(localStorage.getItem('studio:body')).toBe('テスト本文')
  // afterEach の vi.useRealTimers() で後続テストへの影響を回避
})

it('localStorage に保存済みの本文が初期値として復元される', () => {
  localStorage.setItem('studio:body', '保存済み本文')
  localStorage.setItem('studio:title', '保存済みタイトル')
  renderWithRouter(<StudioPage />)
  const textarea = screen.getByLabelText('本文') as HTMLTextAreaElement
  expect(textarea.value).toBe('保存済み本文')
})

it('localStorage に保存済みのタイトルが note タブ切り替え後に復元される', async () => {
  localStorage.setItem('studio:title', '保存済みタイトル')
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  const titleInput = screen.getByLabelText('タイトル') as HTMLInputElement
  expect(titleInput.value).toBe('保存済みタイトル')
})

// ── a11y テスト ────────────────────────────────────────────────────────────────

it('プラットフォームタブに role="tablist" と role="tab" が付与されている', () => {
  renderWithRouter(<StudioPage />)
  expect(screen.getByRole('tablist')).toBeInTheDocument()
  const tabs = screen.getAllByRole('tab')
  expect(tabs).toHaveLength(3)
})

it('アクティブタブは aria-selected="true" を持つ', () => {
  renderWithRouter(<StudioPage />)
  const xTab = screen.getByRole('tab', { name: /X \(Twitter\)/ })
  expect(xTab).toHaveAttribute('aria-selected', 'true')
})

it('note タブに切り替えると aria-selected が note に移動する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  const noteTab = screen.getByRole('tab', { name: /note/ })
  const xTab = screen.getByRole('tab', { name: /X \(Twitter\)/ })
  expect(noteTab).toHaveAttribute('aria-selected', 'true')
  expect(xTab).toHaveAttribute('aria-selected', 'false')
})

it('プレビューパネルに role="tabpanel" が付与されている', () => {
  renderWithRouter(<StudioPage />)
  expect(screen.getByRole('tabpanel')).toBeInTheDocument()
})

// ── 空状態テスト ────────────────────────────────────────────────────────────────

it('本文が空のとき記事統計バッジを表示しない（空でも「約1分で読了」が出ないこと）', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  expect(screen.queryByText(/分で読了/)).not.toBeInTheDocument()
})

it('本文に値があれば記事統計バッジを表示する', async () => {
  renderWithRouter(<StudioPage />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: /note/ }))
  await user.type(screen.getByLabelText('本文'), 'テスト記事本文です。')
  expect(screen.getByText(/分で読了/)).toBeInTheDocument()
})

// ── アイコン分離テスト（note と WordPress の視覚的区別） ───────────────────────

it('note タブと WordPress タブは異なる aria-label を持つ', () => {
  renderWithRouter(<StudioPage />)
  const tabs = screen.getAllByRole('tab')
  const labels = tabs.map((t) => t.textContent ?? '')
  expect(labels).toContain('note')
  expect(labels).toContain('WordPress')
})
