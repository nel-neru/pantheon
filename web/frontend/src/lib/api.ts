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

// SSE streaming helper — calls callback for each parsed event
export function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
  onDone?: () => void,
  onError?: (e: Error) => void
): AbortController {
  const ctrl = new AbortController()
  ;(async () => {
    try {
      const res = await fetch(`${BASE}${path}`, {
        method: 'POST',
        headers: withAuth({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) {
        if (res.status === 401) notifyUnauthorized()
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail ?? `HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              onEvent(JSON.parse(line.slice(6)))
            } catch {}
          }
        }
      }
      onDone?.()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        onError?.(e as Error)
      }
    }
  })()
  return ctrl
}
