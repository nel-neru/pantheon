// API トークン保管（web/frontend と同じ規約・同じ localStorage キーを共有）。
// バックエンドで PANTHEON_API_TOKEN が設定されている場合、Atelier も全 /api と
// /ws にこのトークンを付与する。URL の ?token=xxx を一度だけ取り込み、以降は
// localStorage から読む（履歴にトークンを残さない）。
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

export function withAuth(headers: Record<string, string> = {}): Record<string, string> {
  const token = getApiToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

export function appendTokenToWsUrl(url: string): string {
  const token = getApiToken()
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}
