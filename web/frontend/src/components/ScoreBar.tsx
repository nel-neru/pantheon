import type { CSSProperties } from 'react'

import { cn, healthClass } from '@/lib/utils'

/**
 * 全画面共通のスコアバー（C033）。一覧/詳細で二重定義されていたしきい値・配色を統一する。
 * 幅は inline style ではなく CSS 変数 `--score-width` 経由で渡す（動的値のみ・見た目はCSS側）。
 */
export function ScoreBar({
  score,
  showValue = true,
  label,
}: {
  score: number
  showValue?: boolean
  label?: string
}) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0))
  const tone = healthClass(clamped) // good | warning | critical
  const widthVar = { '--score-width': `${clamped}%` } as CSSProperties

  return (
    <div
      className="score-bar"
      role="meter"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? 'スコア'}
    >
      <div className="score-bar-track">
        <div className={cn('score-bar-fill', `score-${tone}`)} style={widthVar} />
      </div>
      {showValue ? <span className="score-bar-value">{Math.round(clamped)}</span> : null}
    </div>
  )
}
