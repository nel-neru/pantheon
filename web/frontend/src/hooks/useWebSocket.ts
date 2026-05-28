import { useCallback, useEffect, useRef, useState } from 'react'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type IncomingSocketMessage = {
  type?: 'message' | 'status' | 'error'
  content?: unknown
}

function createMessage(role: ChatMessage['role'], content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
  }
}

function getSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

export function useWebSocket(url = getSocketUrl()) {
  const [connected, setConnected] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [typing, setTyping] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  const appendMessage = useCallback((role: ChatMessage['role'], content: string) => {
    setMessages((current) => [...current, createMessage(role, content)])
  }, [])

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
          const payload = JSON.parse(event.data) as IncomingSocketMessage
          const text = typeof payload.content === 'string' ? payload.content : ''

          if (payload.type === 'message') {
            setTyping(false)
            appendMessage('assistant', text)
            return
          }

          if (payload.type === 'status') {
            if (/done|complete|idle|ready/i.test(text)) {
              setTyping(false)
            } else if (text) {
              setTyping(true)
            }
            return
          }

          if (payload.type === 'error') {
            setTyping(false)
            appendMessage('assistant', text || 'The chat service returned an error.')
          }
        } catch {
          setTyping(false)
        }
      }

      socket.onerror = () => {
        setConnected(false)
      }

      socket.onclose = () => {
        setConnected(false)
        setTyping(false)
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
  }, [appendMessage, url])

  const send = useCallback(
    (content: string) => {
      const trimmed = content.trim()
      const socket = socketRef.current

      if (!trimmed || !socket || socket.readyState !== WebSocket.OPEN) {
        return false
      }

      socket.send(JSON.stringify({ message: trimmed }))
      appendMessage('user', trimmed)
      setTyping(true)
      return true
    },
    [appendMessage],
  )

  return { connected, send, messages, typing }
}
