import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())

// jsdom に欠けている API を最小スタブ（Atelier は canvas / WS / matchMedia を使う）。
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}

// jsdom は canvas 2D を実装しないので null を返す（Firmament は null ガード済み）。
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']

// jsdom の WebSocket は実接続を試みるため、無害なスタブで常に上書きしてネットワークを断つ
// （`'WebSocket' in globalThis` は jsdom で常に true のため、条件付きだとスタブが効かない）。
class FakeSocket {
  onopen: (() => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  close() {}
}
;(globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeSocket

// 既定の fetch は「ネットワーク無し」を返す。各テストで上書きする。
if (!globalThis.fetch) {
  globalThis.fetch = vi.fn(() => Promise.reject(new Error('no network'))) as unknown as typeof fetch
}
