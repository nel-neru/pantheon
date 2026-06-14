import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import {
  CompanyManifestTable,
  type CompanyManifest,
  type CompanyManifestTableProps,
} from '../CompanyManifestTable'

const defaultInstall = (_m: CompanyManifest): Promise<void> => Promise.resolve()

/** props.manifests を省略した場合は [] をデフォルトとするが、
 *  明示的に undefined/null を渡した場合はそれを使う。
 *  'manifests' in props で存在チェックして切り替える。 */
function renderTable(
  props: Partial<Omit<CompanyManifestTableProps, 'manifests' | 'installing' | 'onInstall'>> & {
    manifests?: CompanyManifest[] | null
    installing?: string | null
    onInstall?: (m: CompanyManifest) => Promise<void>
    // loadingState=true のとき manifests を undefined として渡す
    loadingState?: boolean
  } = {}
) {
  const { loadingState, manifests, installing = null, onInstall = defaultInstall, ...rest } = props
  // manifests が明示的に null なら null（エラー状態）、省略なら []（空）、loadingState なら undefined（ローディング）
  const resolvedManifests: CompanyManifest[] | null | undefined = loadingState
    ? undefined
    : manifests === null
      ? null
      : (manifests ?? [])
  return render(
    <MemoryRouter>
      <CompanyManifestTable
        manifests={resolvedManifests}
        installing={installing}
        onInstall={onInstall}
        {...rest}
      />
    </MemoryRouter>
  )
}

const sampleManifests: CompanyManifest[] = [
  {
    id: 'note_sales',
    label: 'note 販売会社',
    genre: 'digital_content',
    description: 'note で販売',
    divisions: ['コンテンツ企画部', '販売部'],
    initial_kpis: ['売上'],
  },
  {
    id: 'x_media',
    label: 'Xメディア会社',
    genre: 'sns',
    description: 'X で収益化',
    divisions: ['SNS部'],
    initial_kpis: [],
  },
]

describe('ローディング状態', () => {
  it('manifests が undefined のときスピナーを表示する', () => {
    renderTable({ loadingState: true })
    expect(screen.getByText('テンプレートを読み込み中…')).toBeInTheDocument()
  })

  it('ローディング中はテーブルを表示しない', () => {
    renderTable({ loadingState: true })
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('エラー状態', () => {
  it('manifests が null のときエラーメッセージを表示する', () => {
    renderTable({ manifests: null, error: 'ネットワークエラー' })
    expect(screen.getByText('テンプレートの読み込みに失敗しました')).toBeInTheDocument()
    expect(screen.getByText('ネットワークエラー')).toBeInTheDocument()
  })

  it('onRetry が渡されたとき再試行ボタンを表示する', () => {
    const onRetry = vi.fn()
    renderTable({ manifests: null, onRetry })
    const btn = screen.getByRole('button', { name: '再試行' })
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('onRetry がないとき再試行ボタンを表示しない', () => {
    renderTable({ manifests: null })
    expect(screen.queryByRole('button', { name: '再試行' })).not.toBeInTheDocument()
  })
})

describe('空状態', () => {
  it('manifests が空配列のときデフォルト空状態テキストを表示する', () => {
    renderTable({ manifests: [] })
    expect(screen.getByText('テンプレートがありません')).toBeInTheDocument()
  })

  it('emptyTitle prop で空状態のタイトルをカスタマイズできる', () => {
    renderTable({ manifests: [], emptyTitle: '会社プラグインがありません。' })
    expect(screen.getByText('会社プラグインがありません。')).toBeInTheDocument()
  })

  it('emptyHint prop で空状態のヒントをカスタマイズできる', () => {
    renderTable({ manifests: [], emptyHint: 'まだプラグインがありません。' })
    expect(screen.getByText('まだプラグインがありません。')).toBeInTheDocument()
  })
})

describe('テーブル表示', () => {
  it('manifests の各行を表示する', () => {
    renderTable({ manifests: sampleManifests })
    expect(screen.getByText('note 販売会社')).toBeInTheDocument()
    expect(screen.getByText('Xメディア会社')).toBeInTheDocument()
  })

  it('initial_kpis がある行は KPI を表示する', () => {
    renderTable({ manifests: sampleManifests })
    expect(screen.getByText('売上')).toBeInTheDocument()
  })

  it('initial_kpis が空の行は「—」を表示する', () => {
    renderTable({ manifests: sampleManifests })
    // Xメディア会社の KPI が「—」
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('showGenreDescription=true のとき「ジャンル / 説明」列を表示する', () => {
    renderTable({ manifests: sampleManifests, showGenreDescription: true })
    expect(screen.getByRole('columnheader', { name: 'ジャンル / 説明' })).toBeInTheDocument()
    expect(screen.getByText('[digital_content]')).toBeInTheDocument()
  })

  it('showGenreDescription=false のとき「ジャンル / 説明」列を表示しない', () => {
    renderTable({ manifests: sampleManifests, showGenreDescription: false })
    expect(screen.queryByRole('columnheader', { name: 'ジャンル / 説明' })).not.toBeInTheDocument()
    expect(screen.queryByText('[digital_content]')).not.toBeInTheDocument()
  })

  it('heading prop でヘッダーをカスタマイズできる', () => {
    renderTable({ manifests: [], heading: 'カスタム見出し' })
    expect(screen.getByText('カスタム見出し')).toBeInTheDocument()
  })

  it('デフォルト installButtonLabel は「この会社を作成」', () => {
    renderTable({ manifests: sampleManifests })
    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    expect(buttons.length).toBe(sampleManifests.length)
  })

  it('installButtonLabel をカスタマイズできる', () => {
    renderTable({ manifests: sampleManifests, installButtonLabel: '作成' })
    const buttons = screen.getAllByRole('button', { name: '作成' })
    expect(buttons.length).toBe(sampleManifests.length)
  })
})

describe('ConfirmDialog ゲート', () => {
  it('インストールボタンをクリックしてもすぐには API を呼ばない', () => {
    const onInstall = vi.fn().mockResolvedValue(undefined)
    renderTable({ manifests: sampleManifests, onInstall })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    expect(onInstall).not.toHaveBeenCalled()
  })

  it('インストールボタンで確認ダイアログが開く', async () => {
    renderTable({ manifests: sampleManifests })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('確認ダイアログのタイトルにマニフェスト名が含まれる', async () => {
    renderTable({ manifests: sampleManifests })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/note 販売会社/)).toBeInTheDocument()
  })

  it('confirmTitle prop でダイアログタイトルをカスタマイズできる', async () => {
    renderTable({
      manifests: sampleManifests,
      confirmTitle: (m) => `${m.label} を起動？`,
    })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('note 販売会社 を起動？')).toBeInTheDocument()
  })

  it('確認ボタンをクリックすると onInstall を呼ぶ', async () => {
    const onInstall = vi.fn().mockResolvedValue(undefined)
    renderTable({ manifests: sampleManifests, onInstall })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'この会社を作成' }))

    await waitFor(() =>
      expect(onInstall).toHaveBeenCalledWith(sampleManifests[0])
    )
  })

  it('キャンセルすると onInstall を呼ばない', async () => {
    const onInstall = vi.fn().mockResolvedValue(undefined)
    renderTable({ manifests: sampleManifests, onInstall })

    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    fireEvent.click(buttons[0])

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'キャンセル' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onInstall).not.toHaveBeenCalled()
  })

  it('confirmLabel prop でダイアログの確認ボタンラベルをカスタマイズできる', async () => {
    renderTable({
      manifests: sampleManifests,
      installButtonLabel: '作成',
      confirmLabel: '作成する',
    })

    fireEvent.click(screen.getAllByRole('button', { name: '作成' })[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: '作成する' })).toBeInTheDocument()
  })
})

describe('ビジー状態', () => {
  it('busy=true のとき全インストールボタンを無効化する', () => {
    renderTable({ manifests: sampleManifests, busy: true })
    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    buttons.forEach((btn) => expect(btn).toBeDisabled())
  })

  it('installing に ID を渡すとその行のボタンが「作成中…」になる', () => {
    renderTable({ manifests: sampleManifests, installing: 'note_sales' })
    expect(screen.getByText('作成中…')).toBeInTheDocument()
  })

  it('installing 中は他の行のボタンも無効化される', () => {
    renderTable({ manifests: sampleManifests, installing: 'note_sales' })
    // note_sales 以外の Xメディア会社 のボタン
    const buttons = screen.getAllByRole('button', { name: 'この会社を作成' })
    buttons.forEach((btn) => expect(btn).toBeDisabled())
  })
})
