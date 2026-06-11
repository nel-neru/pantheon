import { useEffect, useRef, useState } from 'react'

import { appendTokenToWsUrl } from '@/lib/token'

export type LiveEvent = {
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

function socketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return appendTokenToWsUrl(`${protocol}//${window.location.host}/ws/updates`)
}

// プラットフォーム横断のライブイベント購読（自動再接続つき）。
export function useLiveFeed(max = 40) {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<LiveEvent[]>([])
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let active = true
    let reconnect: number | undefined
    const url = socketUrl()

    const connect = () => {
      if (!active) return
      let socket: WebSocket
      try {
        socket = new WebSocket(url)
      } catch {
        reconnect = window.setTimeout(connect, 3000)
        return
      }
      socketRef.current = socket

      socket.onopen = () => active && setConnected(true)
      socket.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data) as LiveEvent
          setEvents((cur) => [payload, ...cur].slice(0, max))
        } catch {
          // ignore malformed frames
        }
      }
      socket.onerror = () => setConnected(false)
      socket.onclose = () => {
        setConnected(false)
        if (active) reconnect = window.setTimeout(connect, 3000)
      }
    }

    connect()
    return () => {
      active = false
      if (reconnect) window.clearTimeout(reconnect)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [max])

  return { connected, events }
}
