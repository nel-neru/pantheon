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

// ─── Typed convenience wrappers ──────────────────────────────────────────────

export type DaemonState = {
  name: string
  running: boolean
  pid?: number | null
  last_heartbeat?: string | null
  desired?: string | null
}

export type DaemonsStatusResponse = {
  daemons: Record<string, DaemonState>
  rate_limited?: boolean
}

export async function getDaemonsStatus(): Promise<DaemonsStatusResponse> {
  return api<DaemonsStatusResponse>('GET', '/api/daemons/status')
}

export async function startRevenueDaemon(opts: {
  target?: number
  source_org?: string
  min_reach?: number
}): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>('POST', '/api/daemons/revenue/start', opts)
}

export async function stopRevenueDaemon(): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>('POST', '/api/daemons/revenue/stop')
}

export async function importOutcomes(body: {
  rows: Record<string, unknown>[]
  org_name?: string
}): Promise<{ imported: number; skipped: number; orgs: string[] }> {
  return api<{ imported: number; skipped: number; orgs: string[] }>(
    'POST',
    '/api/outcomes/import',
    body
  )
}

export type BusinessHandoffRoute = {
  from_org: string
  to_org: string
  kind: string
}

export type Business = {
  id: string
  name: string
  purpose: string
  member_orgs: string[]
  roles: Record<string, string>
  handoff_routes: BusinessHandoffRoute[]
  kpis: string[]
  status: string
  created_at: string
}

export type BusinessOutcomes = {
  business: Business
  member_orgs: string[]
  by_metric: Record<string, number>
  event_count: number
  total_revenue: number
  total_reach: number
}

export async function listBusinesses(): Promise<{ businesses: Business[] }> {
  return api<{ businesses: Business[] }>('GET', '/api/businesses')
}

export async function createBusiness(body: {
  name: string
  purpose?: string
  member_orgs?: string[]
  roles?: Record<string, string>
  handoff_routes?: BusinessHandoffRoute[]
  kpis?: string[]
}): Promise<Business> {
  return api<Business>('POST', '/api/businesses', body)
}

export async function getBusiness(id: string): Promise<Business> {
  return api<Business>('GET', `/api/businesses/${encodeURIComponent(id)}`)
}

export async function getBusinessOutcomes(id: string): Promise<BusinessOutcomes> {
  return api<BusinessOutcomes>('GET', `/api/businesses/${encodeURIComponent(id)}/outcomes`)
}

export async function composeBusiness(id: string): Promise<{ created: number; handoff_ids: string[] }> {
  return api<{ created: number; handoff_ids: string[] }>('POST', `/api/businesses/${encodeURIComponent(id)}/compose`)
}

export async function patchBusiness(
  id: string,
  body: {
    name?: string
    purpose?: string
    status?: 'active' | 'paused' | 'archived'
    member_orgs?: string[]
    roles?: Record<string, string>
    kpis?: string[]
  }
): Promise<Business> {
  return api<Business>('PATCH', `/api/businesses/${encodeURIComponent(id)}`, body)
}

export async function deleteBusiness(id: string): Promise<{ ok: boolean; deleted: boolean }> {
  return api<{ ok: boolean; deleted: boolean }>('DELETE', `/api/businesses/${encodeURIComponent(id)}`)
}

export type WindowUsageSummary = {
  window_hours: number
  calls: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  total_tokens: number
  total_cost_usd: number
  measured_calls: number
  estimated_calls: number
}

export type UsageSummaryResponse = {
  usage: {
    session_5h: WindowUsageSummary
    weekly_7d: WindowUsageSummary
  }
  governor: {
    enabled: boolean
    level: string
    window_hours: number
    window_tokens: number
    soft_limit_tokens: number
    hard_limit_tokens: number
  }
  rate_limited: boolean
  retry_at?: string | null
  rate_limit_scope?: string | null
}

export async function getUsageSummary(): Promise<UsageSummaryResponse> {
  return api<UsageSummaryResponse>('GET', '/api/usage/summary')
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
