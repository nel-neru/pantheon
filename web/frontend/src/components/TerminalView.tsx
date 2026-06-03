import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

/**
 * 実PTYに接続する埋め込みターミナル(xterm.js)。
 * sessionId ごとに WebSocket /ws/terminal/{id} へ接続し、入出力をブリッジする。
 */
export function TerminalView({ sessionId, onExit }: { sessionId: string; onExit?: () => void }) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return undefined

    const term = new Terminal({
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
      cursorBlink: true,
      convertEol: false,
      theme: {
        background: '#0d1117',
        foreground: '#e6edf3',
        cursor: '#58a6ff',
        selectionBackground: 'rgba(56,139,253,0.3)',
      },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host)
    try {
      fit.fit()
    } catch {
      /* noop */
    }

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/terminal/${sessionId}`)
    ws.binaryType = 'arraybuffer'

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }))
      }
    }

    ws.onopen = () => sendResize()
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'exit') {
            term.write(`\r\n\x1b[33m[プロセス終了 code=${msg.exit_code ?? '?'}]\x1b[0m\r\n`)
            onExit?.()
          } else if (msg.type === 'error') {
            term.write(`\r\n\x1b[31m${msg.message}\x1b[0m\r\n`)
          }
        } catch {
          /* ignore non-JSON text */
        }
      } else {
        term.write(new Uint8Array(event.data as ArrayBuffer))
      }
    }

    const dataDisposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    const handleResize = () => {
      try {
        fit.fit()
      } catch {
        /* noop */
      }
      sendResize()
    }
    window.addEventListener('resize', handleResize)
    const observer = new ResizeObserver(handleResize)
    observer.observe(host)
    term.focus()

    return () => {
      window.removeEventListener('resize', handleResize)
      observer.disconnect()
      dataDisposable.dispose()
      try {
        ws.close()
      } catch {
        /* noop */
      }
      term.dispose()
    }
  }, [sessionId, onExit])

  return <div ref={hostRef} className="terminal-host" />
}
