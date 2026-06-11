// API トークン保管。バックエンドで PANTHEON_API_TOKEN を設定した場合、GUI は
// 全 /api リクエストと /ws 接続にこのトークンを付与する必要がある。
// 取得方法: URL の ?token=xxx を一度だけ取り込んで localStorage に保存し、
// 以降は localStorage から読む（URL からはトークンを除去して履歴に残さない）。
const STORAGE_KEY = 'pantheon_api_token'

function captureTokenFromUrl(): void {
  if (typeof window === 'undefined') return
  try {
    const params = new URLSearchParams(window.location.search)
    const t = params.get('token')
    if (t) {
      localStorage.setItem(STORAGE_KEY, t)
      params.delete('token')
      const qs = params.toString()
      const next = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash
      window.history.replaceState({}, '', next)
    }
  } catch {
    // localStorage / history が使えない環境では何もしない
  }
}

captureTokenFromUrl()

export function getApiToken(): string {
  if (typeof window === 'undefined') return ''
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setApiToken(token: string): void {
  if (typeof window === 'undefined') return
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // 保存に失敗しても致命ではない
  }
}

// トークン設定時のみ Authorization ヘッダを付与する。
export function withAuth(headers: Record<string, string> = {}): Record<string, string> {
  const token = getApiToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

// WebSocket URL にトークンをクエリ付与する（ブラウザは WS にヘッダを付けられない）。
export function appendTokenToWsUrl(url: string): string {
  const token = getApiToken()
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}
