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
