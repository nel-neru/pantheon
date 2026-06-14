import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { appendTokenToWsUrl } from '../lib/token'

export type PlatformUpdate = {
  id?: string
  type?: string
  operation?: string
  status?: string
  title?: string
  details?: string
  org_name?: string | null
  entity_type?: string | null
  entity_id?: string | null
  route?: string | null
  timestamp?: string
}

function getSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return appendTokenToWsUrl(`${protocol}//${window.location.host}/ws/updates`)
}

type PlatformUpdatesValue = { connected: boolean; offline: boolean; events: PlatformUpdate[] }

// Provider 未装着でも安全に動く既定値（個別ページのテストは Provider 無しで描画される）。
const PlatformUpdatesContext = createContext<PlatformUpdatesValue>({
  connected: false,
  offline: false,
  events: [],
})

/**
 * アプリ全体で 1 本の WebSocket を共有する Provider（C009）。
 *
 * 以前は usePlatformUpdates() を呼ぶたびに new WebSocket していたため、App＋各ページ
 * （Inbox/ContentSchedule/Sessions/OrchestraView）で接続が多重化し、同一イベントが
 * N 重に処理・再取得を誘発していた。Provider で 1 接続に集約し、各ページは購読のみにする。
 */
export function PlatformUpdatesProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const [offline, setOffline] = useState(false)
  const [events, setEvents] = useState<PlatformUpdate[]>([])
  const socketRef = useRef<WebSocket | null>(null)
  const attemptsRef = useRef(0)

  useEffect(() => {
    let active = true
    let reconnectTimer: number | undefined
    const url = getSocketUrl()

    const connect = () => {
      if (!active) return

      const socket = new WebSocket(url)
      socketRef.current = socket

      socket.onopen = () => {
        attemptsRef.current = 0
        setConnected(true)
        setOffline(false)
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as PlatformUpdate
          setEvents((current) => [payload, ...current].slice(0, 30))
        } catch {
          // ignore invalid payloads
        }
      }

      socket.onerror = () => {
        setConnected(false)
      }

      socket.onclose = () => {
        setConnected(false)
        if (active) {
          // 再接続を繰り返しても回復しない＝恒久的なオフラインへ昇格（C035）。
          attemptsRef.current += 1
          if (attemptsRef.current >= 3) setOffline(true)
          reconnectTimer = window.setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      active = false
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [])

  return createElement(
    PlatformUpdatesContext.Provider,
    { value: { connected, offline, events } },
    children,
  )
}

export function usePlatformUpdates(): PlatformUpdatesValue {
  return useContext(PlatformUpdatesContext)
}
