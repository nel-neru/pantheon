// 小さな表示用フォーマッタ群。

export function pad2(n: number): string {
  const v = Number.isFinite(n) ? n : 0
  return String(Math.max(0, Math.floor(v))).padStart(2, '0')
}

export function compactNumber(n: number): string {
  if (!Number.isFinite(n)) return '0'
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(Math.round(n))
}

export function percent(value: number, digits = 0): string {
  // 非有限値（欠落フィールド由来の NaN/±Infinity）は 0% に倒す。compactNumber と
  // 同じ finite-safe 規約に揃え、free-form payload で 'NaN%' を出荷しない。
  if (!Number.isFinite(value)) return `${(0).toFixed(digits)}%`
  const v = value <= 1 ? value * 100 : value
  return `${v.toFixed(digits)}%`
}

export function relativeTime(iso: string | undefined | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const diff = Date.now() - d.getTime()
  const min = Math.round(diff / 60000)
  if (min < 1) return 'たった今'
  if (min < 60) return `${min}分前`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}時間前`
  const day = Math.round(hr / 24)
  return `${day}日前`
}

// Deterministic 0..1 hash from a string — used to seed art positions without RNG.
export function seedFrom(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 100000) / 100000
}

export function clamp(value: number, lo: number, hi: number): number {
  // 非有限値は下限 lo に倒す。Math.max/min は NaN を伝播させる（Math.min(hi, NaN)=NaN）ため、
  // ガードしないと clamp 後も NaN が残り width:`${NaN}%` でバーが無言で壊れる。
  if (!Number.isFinite(value)) return lo
  return Math.min(hi, Math.max(lo, value))
}
