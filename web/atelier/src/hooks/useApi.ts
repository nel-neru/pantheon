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
  // 直近に開始したリクエストの連番。ポーリング（interval は前回を await しない）や path 変更で
  // 複数リクエストが同時に飛び、遅い古い応答が新しい応答を上書きする順序逆転を防ぐ。最新の id を
  // 持つ応答だけが commit できる（Inbox.tsx の reqRef ガードと同型）。
  const seq = useRef(0)

  const run = useCallback(async () => {
    if (!path) return
    const id = ++seq.current
    try {
      const result = await api<T>('GET', path)
      if (alive.current && id === seq.current) {
        setData(result)
        setError(null)
      }
    } catch (e) {
      if (alive.current && id === seq.current) setError((e as Error).message)
    } finally {
      if (alive.current && id === seq.current) setLoading(false)
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
