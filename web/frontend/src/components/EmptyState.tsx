import type { ComponentType, ReactNode } from 'react'

type IconType = ComponentType<{ size?: number; className?: string }>

/**
 * 全画面共通の空/エラー表示の中身（C023）。アイコンサイズ・余白の揺れを統一する。
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
}: {
  icon?: IconType
  title: ReactNode
  hint?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      {Icon ? <Icon className="empty-state-icon" size={28} /> : null}
      <h3>{title}</h3>
      {hint ? <p>{hint}</p> : null}
      {action ?? null}
    </div>
  )
}
