import type { ReactNode } from 'react'

import { cn } from '@/lib/cn'
import { pad2 } from '@/lib/format'

// 展示ヘッダー：各ページを美術館のプレートのように開く。
export function Exhibit({
  index,
  kicker,
  title,
  lede,
  actions,
}: {
  index: number
  kicker: string
  title: ReactNode
  lede?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="exhibit rise">
      <div className="exhibit-index">
        <span className="no">No. {pad2(index)}</span>
        <span className="kicker">{kicker}</span>
        <span className="line" />
      </div>
      <div className="flex flex-wrap items-end justify-between gap-8">
        <h1 className="exhibit-title">{title}</h1>
        {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
      </div>
      {lede ? <p className="exhibit-lede">{lede}</p> : null}
    </header>
  )
}

export function Plate({
  no,
  className,
  children,
}: {
  no?: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('plate', className)}>
      {no ? <span className="plate-no">{no}</span> : null}
      {children}
    </div>
  )
}

export function Stat({
  label,
  value,
  sub,
  tone = 'gold',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'gold' | 'ice' | 'plain'
}) {
  const color = tone === 'gold' ? 'var(--gold)' : tone === 'ice' ? 'var(--ice)' : 'var(--text)'
  return (
    <div className="flex flex-col gap-2">
      <span className="kicker">{label}</span>
      <span className="figure-stat" style={{ color }}>
        {value}
      </span>
      {sub ? <span className="text-faint mono text-[11px] tracking-wider">{sub}</span> : null}
    </div>
  )
}

export function Tag({
  children,
  tone = 'neutral',
  live,
}: {
  children: ReactNode
  tone?: 'neutral' | 'gold' | 'ice' | 'rose' | 'green'
  live?: boolean
}) {
  const cls =
    tone === 'gold'
      ? 'tag-gold'
      : tone === 'ice'
        ? 'tag-ice'
        : tone === 'rose'
          ? 'tag-rose'
          : tone === 'green'
            ? 'tag-green'
            : ''
  return (
    <span className={cn('tag', cls)}>
      {live ? <span className="dot dot-live" /> : null}
      {children}
    </span>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="serif text-2xl text-dim" style={{ fontStyle: 'italic' }}>
        {title}
      </div>
      {hint ? <div className="mono text-faint text-[11px] tracking-wider">{hint}</div> : null}
    </div>
  )
}

export function Loading({ label = '観測中' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-16 text-dim">
      <span className="dot dot-live text-gold" />
      <span className="mono text-[11px] tracking-[0.2em] uppercase">{label}…</span>
    </div>
  )
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <Plate>
      <div className="kicker mb-2" style={{ color: 'var(--rose)' }}>
        接続エラー
      </div>
      <p className="text-dim text-sm">
        バックエンド（<span className="mono">pantheon serve</span>）に接続できません。{message}
      </p>
    </Plate>
  )
}
