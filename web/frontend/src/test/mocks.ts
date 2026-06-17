import { vi } from 'vitest'

export const mockApi = vi.fn()
export const mockStreamSSE = vi.fn()

vi.mock('@/lib/api', () => ({
  api: mockApi,
  streamSse: mockStreamSSE,
}))
