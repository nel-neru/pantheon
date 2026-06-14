// 全画面共通のラベル/バッジ語彙の一元定義（C021）。
//
// status / priority / level の「日本語表示」と「バッジ配色」を1箇所に集約し、画面ごとに
// 独自定義していた揺れ（同じ pending が黄/灰でばらつく、英語生値の露出など）を解消する。

export type BadgeClass = 'badge-neutral' | 'badge-blue' | 'badge-green' | 'badge-yellow' | 'badge-red'

const STATUS_LABEL: Record<string, string> = {
  pending: '保留',
  proposed: '未対応',
  queued: '待機中',
  in_progress: '処理中',
  running: '実行中',
  active: '稼働中',
  completed: '完了',
  done: '完了',
  success: '成功',
  approved: '承認済み',
  rejected: '却下',
  failed: '失敗',
  error: 'エラー',
  cancelled: 'キャンセル',
  canceled: 'キャンセル',
  handed_off: '公開確認待ち',
  consumed: '消費済み',
  skipped: 'スキップ',
}

const STATUS_BADGE: Record<string, BadgeClass> = {
  completed: 'badge-green',
  done: 'badge-green',
  success: 'badge-green',
  approved: 'badge-green',
  active: 'badge-green',
  running: 'badge-blue',
  in_progress: 'badge-blue',
  queued: 'badge-yellow',
  pending: 'badge-yellow',
  proposed: 'badge-yellow',
  handed_off: 'badge-yellow',
  failed: 'badge-red',
  error: 'badge-red',
  rejected: 'badge-red',
  consumed: 'badge-blue',
  cancelled: 'badge-neutral',
  canceled: 'badge-neutral',
  skipped: 'badge-neutral',
}

export function statusLabel(value?: string | null): string {
  if (!value) return '—'
  return STATUS_LABEL[value.toLowerCase()] ?? value
}

export function statusBadge(value?: string | null): BadgeClass {
  if (!value) return 'badge-neutral'
  return STATUS_BADGE[value.toLowerCase()] ?? 'badge-neutral'
}

const PRIORITY_LABEL: Record<string, string> = {
  critical: '最優先',
  high: '高',
  medium: '中',
  low: '低',
}

export function priorityLabel(value?: string | null): string {
  if (!value) return '—'
  return PRIORITY_LABEL[value.toLowerCase()] ?? value
}

export function priorityBadge(value?: string | null): BadgeClass {
  const v = (value ?? '').toLowerCase()
  if (v === 'critical' || v === 'high') return 'badge-red'
  if (v === 'medium') return 'badge-yellow'
  return 'badge-neutral'
}

const LEVEL_LABEL: Record<string, string> = {
  info: '情報',
  success: '成功',
  warning: '警告',
  error: 'エラー',
  pending: '処理中',
  done: '完了',
}

export function levelLabel(value?: string | null): string {
  if (!value) return '—'
  return LEVEL_LABEL[value.toLowerCase()] ?? value
}

export function levelBadge(value?: string | null): BadgeClass {
  const v = (value ?? '').toLowerCase()
  if (v === 'error') return 'badge-red'
  if (v === 'warning' || v === 'pending') return 'badge-yellow'
  if (v === 'success' || v === 'done') return 'badge-green'
  if (v === 'info') return 'badge-blue'
  return 'badge-neutral'
}
