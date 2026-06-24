import { vi } from 'vitest'

export const mockApi = vi.fn()
export const mockStreamSSE = vi.fn()
export const mockEditVaultNote = vi.fn()
export const mockSyncVault = vi.fn()
export const mockGetVaultGraph = vi.fn()

vi.mock('@/lib/api', () => ({
  api: mockApi,
  streamSse: mockStreamSSE,
  editVaultNote: mockEditVaultNote,
  syncVault: mockSyncVault,
  getVaultGraph: mockGetVaultGraph,
}))
