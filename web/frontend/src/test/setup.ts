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
