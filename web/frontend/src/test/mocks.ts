import { vi } from 'vitest'

export const mockApi = vi.fn()

vi.mock('@/lib/api', () => ({
  api: mockApi,
}))
