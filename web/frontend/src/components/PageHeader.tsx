import type { ReactNode } from 'react'

/**
 * 全画面共通のページヘッダ（C023）。タイトル/サブタイトル/右側アクションの構造を統一する。
 * （従来は div.page-title 直書き・page wrapper・h1 等3系統に分裂し subtitle も未スタイルだった）
 */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div className="page-title-wrap">
        <div className="page-title">{title}</div>
        {subtitle ? <div className="page-subtitle">{subtitle}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  )
}
