import { AlertTriangle } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'

import { EmptyState } from './EmptyState'

type IconType = ComponentType<{ size?: number; className?: string }>

/**
 * 全画面共通の非同期状態ラッパ（C011/C023）。loading / error（再試行つき）/ empty / 本体 を
 * 統一描画する。これにより「失敗を握りつぶして空カード」「loading が素テキストとスピナーで割れる」
 * といった画面間の分裂を解消する。
 */
export function AsyncBoundary({
  loading,
  error,
  isEmpty = false,
  onRetry,
  loadingText = '読み込み中…',
  errorTitle = '読み込みに失敗しました',
  emptyIcon,
  emptyTitle = 'データがありません',
  emptyHint,
  children,
}: {
  loading: boolean
  error?: string | null
  isEmpty?: boolean
  onRetry?: () => void
  loadingText?: ReactNode
  errorTitle?: ReactNode
  emptyIcon?: IconType
  emptyTitle?: ReactNode
  emptyHint?: ReactNode
  children: ReactNode
}) {
  if (loading) {
    return (
      <div className="card">
        <div className="card-body flex items-center gap-3">
          <div className="spinner" />
          <div className="text-muted">{loadingText}</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div className="card-body">
          <EmptyState
            icon={AlertTriangle}
            title={errorTitle}
            hint={error}
            action={
              onRetry ? (
                <button type="button" className="btn btn-secondary" onClick={onRetry}>
                  再試行
                </button>
              ) : undefined
            }
          />
        </div>
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className="card">
        <div className="card-body">
          <EmptyState icon={emptyIcon} title={emptyTitle} hint={emptyHint} />
        </div>
      </div>
    )
  }

  return <>{children}</>
}
