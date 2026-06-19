import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { useApi } from '@/hooks/useApi'

// `api` をモックして応答の解決順を手動制御する（順序逆転レースの再現）。
vi.mock('@/lib/api', () => ({ api: vi.fn() }))

const mockedApi = vi.mocked(api)

afterEach(() => {
  vi.clearAllMocks()
})

/** 外部から解決/拒否できる遅延 Promise を作る。 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useApi', () => {
  it('初回取得が解決すると data に反映される', async () => {
    mockedApi.mockResolvedValueOnce({ value: 1 })
    const { result } = renderHook(() => useApi<{ value: number }>('/api/thing'))

    await waitFor(() => expect(result.current.data).toEqual({ value: 1 }))
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('順序逆転: 古いリクエストが後で解決しても新しい応答を上書きしない', async () => {
    // refetch を2回連続で発火し、1回目（古い）を2回目（新しい）より後に解決させる。
    const first = deferred<{ tick: number }>()
    const second = deferred<{ tick: number }>()
    mockedApi.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const { result } = renderHook(() => useApi<{ tick: number }>('/api/thing'))

    // 2本目（最新）を発火 → 計2リクエストが in-flight。
    act(() => {
      result.current.refetch()
    })

    // 最新（2本目）を先に解決 → commit される。
    await act(async () => {
      second.resolve({ tick: 2 })
    })
    await waitFor(() => expect(result.current.data).toEqual({ tick: 2 }))

    // 古い（1本目）を後から解決 → seq ガードで破棄され、最新を上書きしない。
    await act(async () => {
      first.resolve({ tick: 1 })
    })
    // マイクロタスクを消化しても data は最新のまま。
    await Promise.resolve()
    expect(result.current.data).toEqual({ tick: 2 })
  })

  it('順序逆転: 古いリクエストのエラーが新しい成功応答を上書きしない', async () => {
    const first = deferred<{ ok: boolean }>()
    const second = deferred<{ ok: boolean }>()
    mockedApi.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const { result } = renderHook(() => useApi<{ ok: boolean }>('/api/thing'))
    act(() => {
      result.current.refetch()
    })

    await act(async () => {
      second.resolve({ ok: true })
    })
    await waitFor(() => expect(result.current.data).toEqual({ ok: true }))

    // 古いリクエストを reject → 破棄され error は立たない。
    await act(async () => {
      first.reject(new Error('stale boom'))
    })
    await Promise.resolve()
    expect(result.current.error).toBeNull()
    expect(result.current.data).toEqual({ ok: true })
  })
})
