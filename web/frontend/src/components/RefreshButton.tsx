import { RefreshCw } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 全画面共通の「更新」ボタン（C038）。呼称を「更新」に統一し、aria-label と可視テキストを
 * 一致させる。busy 中はアイコンを回転＋無効化する。
 */
export function RefreshButton({
  onClick,
  busy = false,
  label = '更新',
  className,
}: {
  onClick: () => void
  busy?: boolean
  label?: string
  className?: string
}) {
  return (
    <button
      type="button"
      className={cn('btn btn-secondary btn-sm', className)}
      onClick={onClick}
      disabled={busy}
      aria-label={label}
    >
      <RefreshCw size={14} className={busy ? 'spin' : undefined} aria-hidden="true" />
      {label}
    </button>
  )
}
