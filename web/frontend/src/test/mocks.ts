import { vi } from 'vitest'

export const mockApi = vi.fn()
// SSE は本番から廃止（C037）。各ページテストが beforeEach で reset する後方互換のためのダミー。
export const mockStreamSSE = vi.fn()

vi.mock('@/lib/api', () => ({
  api: mockApi,
}))
