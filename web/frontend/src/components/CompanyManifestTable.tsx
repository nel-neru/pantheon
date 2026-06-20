import { useState, type ReactNode } from 'react'
import { Building2, PackageOpen, Plus } from 'lucide-react'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'

export type CompanyManifest = {
  id: string
  label: string
  genre?: string
  description?: string
  divisions: string[]
  initial_kpis?: string[]
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

export type CompanyManifestTableProps = {
  /**
   * マニフェスト一覧。
   *   undefined = ローディング中
   *   null      = エラー発生
   *   []        = 空（テンプレートなし）
   *   [...] = 通常リスト
   */
  manifests: CompanyManifest[] | undefined | null
  /** エラーメッセージ（manifests が null のとき表示） */
  error?: string | null
  /** 現在インストール中のプラグイン ID（その行のボタンをスピナーに変える） */
  installing: string | null
  /** 他の操作でビジー状態（ボタンを全無効化する） */
  busy?: boolean
  /** 「作成」ボタンのラベル（省略時: 'この会社を作成'） */
  installButtonLabel?: string
  /** 確認ダイアログの confirmLabel（省略時: installButtonLabel と同じ） */
  confirmLabel?: string
  /** 確認ダイアログのタイトル生成（省略時: `「{label}」を作成しますか？`） */
  confirmTitle?: (manifest: CompanyManifest) => string
  /** 確認ダイアログの説明生成（省略時: divisions + description を列挙） */
  confirmDescription?: (manifest: CompanyManifest) => ReactNode
  /**
   * 「ジャンル / 説明」列を表示するか。
   * MarketplacePage = true（デフォルト）、OnboardingPage = false。
   */
  showGenreDescription?: boolean
  /** カードヘッダーの見出しテキスト */
  heading?: string
  /** 見出し下のサブテキスト */
  subtext?: ReactNode
  /** 空状態のタイトル（省略時: 'テンプレートがありません'） */
  emptyTitle?: string
  /** 空状態のヒントテキスト（省略時: '利用可能な会社テンプレートが見つかりませんでした。'） */
  emptyHint?: string
  /** 再試行コールバック（エラー状態で表示される再試行ボタン） */
  onRetry?: () => void
  /**
   * 内部 ConfirmDialog をバイパスして呼び出し側で確認フローを制御したいとき使う。
   * 指定すると「作成」ボタンクリック時に onInstall ではなくこちらが呼ばれる（ダイアログなし）。
   */
  onRequestInstall?: (manifest: CompanyManifest) => void
  /** インストール実行コールバック。ConfirmDialog 確認後に呼ばれる */
  onInstall: (manifest: CompanyManifest) => Promise<void>
}

/**
 * 会社マニフェスト一覧テーブル（OnboardingPage と MarketplacePage の共通部品）。
 *
 * - ローディング／エラー／空状態／テーブル本体を props だけで切替
 * - ConfirmDialog ゲートを内蔵（呼び出し側での boilerplate 不要）
 * - `showGenreDescription` で列構成を変える
 */
export function CompanyManifestTable({
  manifests,
  error,
  installing,
  busy = false,
  installButtonLabel = 'この会社を作成',
  confirmLabel,
  confirmTitle,
  confirmDescription,
  showGenreDescription = true,
  heading,
  subtext,
  emptyTitle,
  emptyHint,
  onRetry,
  onRequestInstall,
  onInstall,
}: CompanyManifestTableProps) {
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

  const resolvedConfirmLabel = confirmLabel ?? installButtonLabel
  const isBusy = busy || installing !== null

  const headingText = heading ?? 'テンプレートから会社を立ち上げる'

  const defaultSubtext = showGenreDescription
    ? 'manifest を選んで「この会社を作成」すると、事業部・Agent・初期KPI・人間タスクまで揃った収益モデル会社（Organization）が即座に立ち上がります。'
    : '作りたい会社を選んで「作成」。複数選んでポートフォリオにできます。'

  const subtextNode = subtext ?? defaultSubtext

  const requestInstall = (m: CompanyManifest) => {
    const title = confirmTitle
      ? confirmTitle(m)
      : `「${m.label}」を作成しますか？`

    const description: ReactNode = confirmDescription
      ? confirmDescription(m)
      : (
        <>
          事業部・Agent・初期KPI・人間タスクまで含む会社を一括生成します。
          {m.divisions.length > 0 && (
            <>
              <br />
              <span className="text-sm text-fg2">作成される事業部: {m.divisions.join('、')}</span>
            </>
          )}
          {m.description && (
            <>
              <br />
              <span className="text-sm text-fg2">{m.description}</span>
            </>
          )}
        </>
      )

    if (onRequestInstall) {
      onRequestInstall(m)
      return
    }
    setConfirm({ title, description, confirmLabel: resolvedConfirmLabel, run: () => onInstall(m) })
  }

  return (
    <>
      <div className="card-body flex flex-col gap-2" id="manifests-table">
        <div className="flex items-center gap-2 mb-1">
          <Building2 size={16} />
          <div className="font-semibold">{headingText}</div>
        </div>
        <p className="text-muted text-sm mb-4">{subtextNode}</p>

        {manifests === undefined ? (
          /* ローディング */
          <div className="flex items-center gap-3">
            <div className="spinner" />
            <div className="text-muted">テンプレートを読み込み中…</div>
          </div>
        ) : manifests === null ? (
          /* エラー */
          <EmptyState
            icon={PackageOpen}
            title="テンプレートの読み込みに失敗しました"
            hint={error ?? undefined}
            action={
              onRetry ? (
                <button type="button" className="btn btn-secondary" onClick={onRetry}>
                  再試行
                </button>
              ) : undefined
            }
          />
        ) : manifests.length === 0 ? (
          /* 空 */
          <EmptyState
            icon={PackageOpen}
            title={emptyTitle ?? 'テンプレートがありません'}
            hint={emptyHint ?? '利用可能な会社テンプレートが見つかりませんでした。'}
          />
        ) : (
          /* テーブル */
          <table className="data-table">
            <thead>
              <tr>
                <th>会社</th>
                {showGenreDescription ? <th>ジャンル / 説明</th> : null}
                <th>事業部</th>
                <th>初期KPI</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {manifests.map((m) => {
                const rowBusy = installing === m.id
                return (
                  <tr key={m.id}>
                    <td className="font-medium">{m.label}</td>
                    {showGenreDescription ? (
                      <td className="text-muted text-sm">
                        {m.genre && <span className="mr-1 text-fg2">[{m.genre}]</span>}
                        {m.description ?? '—'}
                      </td>
                    ) : null}
                    <td className="text-muted text-sm">{m.divisions.join(' / ') || '—'}</td>
                    <td className="text-muted text-sm">
                      {(m.initial_kpis ?? []).length > 0
                        ? (m.initial_kpis ?? []).join(' / ')
                        : '—'}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={isBusy}
                        onClick={() => requestInstall(m)}
                      >
                        {rowBusy ? (
                          <>
                            <div className="spinner" />
                            作成中…
                          </>
                        ) : (
                          <>
                            <Plus size={14} />
                            {installButtonLabel}
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel}
        destructive={false}
        onConfirm={async () => {
          if (confirm) await confirm.run()
        }}
      />
    </>
  )
}
