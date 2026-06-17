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

/**
 * SSE ストリーミング POST ヘルパー。
 * バックエンドの text/event-stream レスポンスを chunk 単位で読み取り、
 * 完全な SSE フレーム（data: <JSON>\n\n）を onEvent コールバックへ渡す。
 * チャンク境界をまたぐ部分フレームをバッファで吸収する。
 */
export async function streamSse(
  path: string,
  body: unknown,
  onEvent: (ev: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: withAuth({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok) {
    if (res.status === 401) notifyUnauthorized()
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }

  if (!res.body) {
    throw new Error('レスポンスボディがありません。')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE フレームは \n\n で区切られる
      const frames = buffer.split('\n\n')
      // 末尾は次チャンクとつながる可能性のある部分フレームとして残す
      buffer = frames.pop() ?? ''

      for (const frame of frames) {
        for (const line of frame.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const jsonStr = trimmed.slice('data:'.length).trim()
          if (!jsonStr) continue
          try {
            const parsed: unknown = JSON.parse(jsonStr)
            if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
              onEvent(parsed as Record<string, unknown>)
            }
          } catch {
            // JSON パース失敗は無視する（不完全なフレームなど）
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
