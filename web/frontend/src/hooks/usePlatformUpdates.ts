import { useEffect, useRef, useState } from 'react'

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
  return `${protocol}//${window.location.host}/ws/updates`
}

export function usePlatformUpdates(url = getSocketUrl()) {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<PlatformUpdate[]>([])
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let active = true
    let reconnectTimer: number | undefined

    const connect = () => {
      if (!active) return

      const socket = new WebSocket(url)
      socketRef.current = socket

      socket.onopen = () => {
        setConnected(true)
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
  }, [url])

  return { connected, events }
}
