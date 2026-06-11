import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'

export type AsyncState<T> = {
  data: T | null
  error: string | null
  loading: boolean
  refetch: () => void
}

// GET 用の薄いデータフック。マウント時に取得し、任意で interval ポーリング。
export function useApi<T>(path: string | null, pollMs = 0): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(Boolean(path))
  const alive = useRef(true)

  const run = useCallback(async () => {
    if (!path) return
    try {
      const result = await api<T>('GET', path)
      if (alive.current) {
        setData(result)
        setError(null)
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    void run()
    let timer: number | undefined
    if (pollMs > 0) {
      timer = window.setInterval(() => void run(), pollMs)
    }
    return () => {
      alive.current = false
      if (timer) window.clearInterval(timer)
    }
  }, [run, pollMs])

  return { data, error, loading, refetch: () => void run() }
}
