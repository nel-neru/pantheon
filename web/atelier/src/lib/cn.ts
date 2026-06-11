// 最小限の className 連結（clsx 不要・依存ゼロ）。
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
