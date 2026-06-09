import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'
import { createElement, type ReactNode } from 'react'
import { afterEach, vi } from 'vitest'

import './mocks'

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
  Toaster: () => null,
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    NavLink: ({
      children,
      to,
      className,
    }: {
      children: ReactNode
      to: string
      className?: string | ((args: { isActive: boolean }) => string)
    }) =>
      createElement(
        'a',
        {
          href: to,
          className: typeof className === 'function' ? className({ isActive: false }) : className,
        },
        children,
      ),
    Link: ({ children, to, className }: { children: ReactNode; to: string; className?: string }) =>
      createElement('a', { href: to, className }, children),
    useNavigate: () => vi.fn(),
  }
})

afterEach(() => {
  cleanup()
})

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

window.HTMLElement.prototype.scrollIntoView = vi.fn()
window.HTMLElement.prototype.scrollTo = vi.fn()

globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})) as unknown as typeof ResizeObserver

// usePlatformUpdates 等が開く WebSocket をテストでは何もしないスタブにする
// （実接続もタイマーも張らないので、ライブ更新を使うページのテストが安定する）。
class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  onopen: ((this: WebSocket, ev: Event) => unknown) | null = null
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null = null
  onerror: ((this: WebSocket, ev: Event) => unknown) | null = null
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null = null
  readyState = MockWebSocket.OPEN
  close = vi.fn()
  send = vi.fn()
  addEventListener = vi.fn()
  removeEventListener = vi.fn()
}
globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
