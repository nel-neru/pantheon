// 媒体別の本文整形ユーティリティ（純ロジック / UI 非依存・テスト可能）。
// 外部依存なし。X のスレッド分割と文字数カウントが中心。

export const X_LIMIT = 280
const THREAD_SUFFIX_RESERVE = 8 // " (12/34)" の最大長を見込んだ予約

// X は概ねコードポイント単位で数える。サロゲートペア(絵文字等)を1として数えるため
// Array.from でコードポイント長を取る（プレビュー用途には十分な近似）。
export function countChars(text: string): number {
  return Array.from(text).length
}

function hardWrap(unit: string, max: number): string[] {
  const chars = Array.from(unit)
  const out: string[] = []
  for (let i = 0; i < chars.length; i += max) {
    out.push(chars.slice(i, i + max).join(''))
  }
  return out
}

// 文末（。．！？!?）と改行で「単位」に分割する（区切り文字は末尾に残す）。
function toUnits(text: string): string[] {
  const rough = text
    .replace(/\r\n/g, '\n')
    .split(/(?<=[。．！？!?\n])/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  return rough.length > 0 ? rough : [text.trim()]
}

// 長文を X のスレッド（番号付き）に分割する。limit 以内なら 1 件のまま返す。
export function splitIntoThread(text: string, limit: number = X_LIMIT): string[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (countChars(trimmed) <= limit) return [trimmed]

  const effective = limit - THREAD_SUFFIX_RESERVE
  const units = toUnits(trimmed).flatMap((u) =>
    countChars(u) > effective ? hardWrap(u, effective) : [u],
  )

  const chunks: string[] = []
  let current = ''
  for (const unit of units) {
    const candidate = current ? `${current} ${unit}` : unit
    if (countChars(candidate) <= effective) {
      current = candidate
    } else {
      if (current) chunks.push(current)
      current = unit
    }
  }
  if (current) chunks.push(current)

  const total = chunks.length
  return chunks.map((chunk, index) => `${chunk} (${index + 1}/${total})`)
}

// note / WordPress 等の記事媒体向けの軽い指標。
export function readingStats(text: string): { chars: number; lines: number; minutes: number } {
  const chars = countChars(text)
  const lines = text.trim() ? text.trim().split(/\n/).length : 0
  // 日本語 ~500字/分 を目安にした概算読了時間。
  const minutes = Math.max(1, Math.round(chars / 500))
  return { chars, lines, minutes }
}
