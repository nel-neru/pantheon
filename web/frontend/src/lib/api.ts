import { withAuth } from './token'

const BASE = ''  // same origin — Vite proxies /api to FastAPI

export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

// 401 集中ハンドリング（C010）。未認証/トークン期限切れを全リクエストで検知して
// アプリ全体に通知し、トークン入力ダイアログ（AuthTokenDialog）を開かせる。
function notifyUnauthorized(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('pantheon:unauthorized'))
  }
}

export async function api<T = unknown>(
  method: ApiMethod,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: withAuth(body ? { 'Content-Type': 'application/json' } : {}),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    if (res.status === 401) notifyUnauthorized()
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as T
}
