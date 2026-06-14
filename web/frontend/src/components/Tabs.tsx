import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type TabItem<T extends string = string> = {
  value: T
  label: ReactNode
  count?: number
}

/**
 * 全画面共通のタブ/フィルタ切替（C038）。ARIA（role=tablist/tab + aria-selected）を備え、
 * 従来 tab-bar / data-tabs / help-tabs の3系統に分裂していたタブ実装を1つに寄せる。
 */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  ariaLabel,
}: {
  tabs: TabItem<T>[]
  value: T
  onChange: (value: T) => void
  ariaLabel?: string
}) {
  return (
    <div className="tab-bar flex items-center gap-2 flex-wrap" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={value === tab.value}
          className={cn('btn btn-sm', value === tab.value ? 'btn-primary' : 'btn-secondary')}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
          {typeof tab.count === 'number' ? (
            <span className="badge badge-neutral">{tab.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  )
}
