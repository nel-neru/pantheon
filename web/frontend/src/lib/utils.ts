import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(value: string | number | Date) {
  const normalized =
    value instanceof Date
      ? value
      : new Date(typeof value === 'number' && value < 1_000_000_000_000 ? value * 1000 : value)

  return normalized.toLocaleString('ja-JP', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 全画面共通の日時/数値フォーマッタ（C022/C038）。
// 画面ごとに散らばっていた toLocaleString()（ロケール無し）/生ISO表示/独自実装を一掃する。

/** 年月日＋時分まで（ja-JP, 2桁ゼロ埋め）。null/空/不正値は「—」。 */
export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const normalized =
    value instanceof Date
      ? value
      : new Date(typeof value === 'number' && value < 1_000_000_000_000 ? value * 1000 : value)
  if (Number.isNaN(normalized.getTime())) return typeof value === 'string' ? value : '—'
  return normalized.toLocaleString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 千区切り整数（ja-JP）。null/不正値は「—」。 */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('ja-JP')
}

/** 円表記（¥1,234）。小数は四捨五入。null/不正値は「—」。 */
export function formatYen(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `¥${Math.round(value).toLocaleString('ja-JP')}`
}

/** スコア表記（既定 0 桁）。null/不正値は「—」。 */
export function formatScore(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

export function healthClass(score: number): 'good' | 'warning' | 'critical' {
  if (score >= 70) return 'good'
  if (score >= 40) return 'warning'
  return 'critical'
}

export function priorityBadge(p: string) {
  if (p === 'high' || p === 'critical') return 'badge-red'
  if (p === 'medium') return 'badge-yellow'
  return 'badge-neutral'
}
