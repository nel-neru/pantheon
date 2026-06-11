// 媒体別の本文整形ユーティリティ（純ロジック / UI 非依存・テスト可能）。
// 外部依存なし。X のスレッド分割と文字数カウントが中心。

export const X_LIMIT = 280

// " (N/N)" 形式の接尾辞が占める文字数を桁数から算出する。
// 例: total=9 → " (1/9)" = 6  total=99 → " (99/99)" = 8  total=999 → " (999/999)" = 10
function suffixReserve(digits: number): number {
  // " (" + digits + "/" + digits + ")" = 2 + digits + 1 + digits + 1 = 4 + 2*digits
  return 4 + 2 * digits
}

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

// 文字列を effective 以内のチャンクに分割する（接尾辞なし）。
function buildChunks(trimmed: string, effective: number): string[] {
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
  return chunks
}

// 長文を X のスレッド（番号付き）に分割する。limit 以内なら 1 件のまま返す。
// 2パス方式: まず仮 reserve で分割し total の桁数を確定 → 必要なら reserve を拡大して再分割。
export function splitIntoThread(text: string, limit: number = X_LIMIT): string[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (countChars(trimmed) <= limit) return [trimmed]

  // パス1: 桁数 2（最小 reserve）で分割して total を推定し、桁数が仮定を上回る限り
  // reserve を拡大して再分割する。再分割で effective が縮みチャンク数が桁境界を
  // 跨ぐことがあり得る（例: 999→1000）ため、1回ではなく桁が安定するまで回す。
  // digits は単調増加し suffixReserve(digits) < limit が上限なので必ず停止する。
  let digits = 2
  let chunks = buildChunks(trimmed, limit - suffixReserve(digits))
  let total = chunks.length

  while (String(total).length > digits && suffixReserve(String(total).length) < limit) {
    digits = String(total).length
    chunks = buildChunks(trimmed, limit - suffixReserve(digits))
    total = chunks.length
  }

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
