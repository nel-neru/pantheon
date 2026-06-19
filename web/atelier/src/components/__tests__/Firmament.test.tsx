/**
 * Firmament.test.tsx
 *
 * Regression tests for the "animation loop mounts once" refactor.
 *
 * The global setup (src/test/setup.ts) stubs getContext → null so Firmament
 * normally early-returns from the setup effect.  Here we locally replace that
 * stub with a minimal 2-D context so the effects actually run, then verify:
 *
 *   Test 1 (regression): poll-driven data updates do NOT restart the RAF loop.
 *   Test 2 (continuity):  data changes still trigger an immediate repaint via
 *                          drawRef (clearRect is called after the rerender).
 */

import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Firmament } from '../Firmament'
import type { OrchestraHandoff, OrchestraSession, OrgSummary } from '@/lib/types'

// ── Minimal canvas-2D context stub ──────────────────────────────────────────

type Ctx2DStub = {
  clearRect: ReturnType<typeof vi.fn>
  beginPath: ReturnType<typeof vi.fn>
  moveTo: ReturnType<typeof vi.fn>
  lineTo: ReturnType<typeof vi.fn>
  stroke: ReturnType<typeof vi.fn>
  arc: ReturnType<typeof vi.fn>
  fill: ReturnType<typeof vi.fn>
  fillText: ReturnType<typeof vi.fn>
  quadraticCurveTo: ReturnType<typeof vi.fn>
  setTransform: ReturnType<typeof vi.fn>
  createRadialGradient: ReturnType<typeof vi.fn>
  fillStyle: string
  strokeStyle: string
  lineWidth: number
  font: string
  textBaseline: string
}

function makeCtxStub(): Ctx2DStub {
  return {
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    quadraticCurveTo: vi.fn(),
    setTransform: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    font: '',
    textBaseline: '',
  }
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

const org1: OrgSummary = {
  id: 'org-1',
  name: 'Alpha',
  purpose: 'test',
  target_repo_path: null,
  status: 'active',
  health_score: 80,
  autonomy_score: 70,
  improvement_velocity: 1,
  total_agents: 3,
  pending_proposals: 2,
  last_active: '2026-06-19T00:00:00Z',
  is_system: false,
  icon_data: null,
}

const org2: OrgSummary = {
  ...org1,
  id: 'org-2',
  name: 'Beta',
}

const session1: OrchestraSession = {
  id: 'sess-1',
  name: 'Evolve',
  status: 'running',
  driver: 'claude',
  agents: [{ agent_id: 'a1', title: 'Reviewer', role: 'review', status: 'running', exit_code: null }],
}

const noHandoffs: OrchestraHandoff[] = []

// ── Setup / teardown ─────────────────────────────────────────────────────────

let ctxStub: Ctx2DStub
let originalGetContext: HTMLCanvasElement['getContext']

beforeEach(() => {
  ctxStub = makeCtxStub()
  // Save the global stub set by setup.ts (returns null) and replace with our rich stub.
  originalGetContext = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = (() =>
    ctxStub as unknown as CanvasRenderingContext2D) as unknown as HTMLCanvasElement['getContext']

  vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(1)
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
})

afterEach(() => {
  HTMLCanvasElement.prototype.getContext = originalGetContext
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Firmament — animation loop lifecycle', () => {
  /**
   * Test 1 (the regression guard).
   *
   * The setup effect (deps:[height]) must run exactly once.  Simulating a poll
   * by passing new array literals of identical content must NOT call getContext
   * a second time or cancel the running RAF.
   *
   * Against the OLD single-effect code (deps:[orgs,sessions,handoffs,theme]):
   *   - getContext would be called twice (setup teardown + re-setup)
   *   - cancelAnimationFrame would be called once (cleanup of first run)
   * → Test 1 FAILS on the old code, PASSES on the fixed code.
   */
  it('Test 1: poll-driven re-render does NOT restart the canvas setup or cancel the RAF loop', () => {
    const { rerender } = render(
      <Firmament
        orgs={[org1]}
        sessions={[session1]}
        handoffs={noHandoffs}
        theme="nocturne"
        height={460}
      />,
    )

    // After initial mount: setup effect ran once → getContext called once.
    const getContextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext')

    // Simulate a poll: pass brand-new array literals with identical content.
    act(() => {
      rerender(
        <Firmament
          orgs={[{ ...org1 }]}
          sessions={[{ ...session1, agents: [...session1.agents] }]}
          handoffs={[]}
          theme="nocturne"
          height={460}
        />,
      )
    })

    // getContext must NOT have been called again (setup effect did not re-run).
    expect(getContextSpy).not.toHaveBeenCalled()

    // cancelAnimationFrame must NOT have been called (loop was not torn down).
    expect(window.cancelAnimationFrame).not.toHaveBeenCalled()
  })

  /**
   * Test 2 (data continuity).
   *
   * Even though the RAF loop is not restarted, a data change must still produce
   * an immediate repaint via drawRef.current?.().  We verify this by asserting
   * that clearRect is called after the rerender with changed data.
   */
  it('Test 2: data change triggers an immediate repaint (clearRect called after rerender)', () => {
    const { rerender } = render(
      <Firmament
        orgs={[org1]}
        sessions={[session1]}
        handoffs={noHandoffs}
        theme="nocturne"
        height={460}
      />,
    )

    // Reset call count so we can isolate the rerender's repaint.
    ctxStub.clearRect.mockClear()

    // Rerender with changed data (add an org).
    act(() => {
      rerender(
        <Firmament
          orgs={[org1, org2]}
          sessions={[session1]}
          handoffs={noHandoffs}
          theme="nocturne"
          height={460}
        />,
      )
    })

    // The data effect calls drawRef.current?.() which calls draw() which calls clearRect.
    expect(ctxStub.clearRect).toHaveBeenCalled()
  })
})
