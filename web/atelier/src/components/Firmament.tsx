import { useEffect, useRef } from 'react'

import { clamp, seedFrom } from '@/lib/format'
import type { OrchestraHandoff, OrchestraSession, OrgSummary } from '@/lib/types'
import type { Theme } from '@/hooks/useTheme'

type Star = {
  key: string
  name: string
  kind: 'org' | 'session'
  hx: number // home position 0..1
  hy: number
  r: number // base radius (px)
  glow: number // 0..1 brightness
  live: boolean
  phase: number
  drift: number
}

type DataSnapshot = {
  stars: Star[]
  orgIndex: Map<string, Star>
  handoffs: OrchestraHandoff[]
  colors: ReturnType<typeof readColors>
}

function readColors(): { gold: string; ice: string; faint: string; text: string } {
  const cs = getComputedStyle(document.documentElement)
  return {
    gold: cs.getPropertyValue('--gold').trim() || '#c9a86a',
    ice: cs.getPropertyValue('--ice').trim() || '#92b9cc',
    faint: cs.getPropertyValue('--text-faint').trim() || '#5f5a50',
    text: cs.getPropertyValue('--text').trim() || '#ece5d8',
  }
}

function buildStars(orgs: OrgSummary[], sessions: OrchestraSession[]): Star[] {
  const stars: Star[] = []
  for (const org of orgs) {
    const s1 = seedFrom(org.name)
    const s2 = seedFrom(org.name + '::y')
    const agents = org.total_agents || 0
    stars.push({
      key: `org:${org.id}`,
      name: org.name,
      kind: 'org',
      hx: 0.08 + s1 * 0.84,
      hy: 0.12 + s2 * 0.76,
      r: clamp(2.4 + Math.sqrt(agents) * 1.5, 2.4, 10),
      glow: clamp(0.35 + (org.health_score || 0) / 140, 0.35, 1),
      live: org.status === 'active' && (org.pending_proposals || 0) > 0,
      phase: s1 * Math.PI * 2,
      drift: 0.5 + s2,
    })
  }
  const liveSessions = sessions.filter((s) => s.status === 'running' || s.status === 'rate_limited')
  for (const sess of liveSessions) {
    const s1 = seedFrom(sess.id)
    const s2 = seedFrom(sess.id + '::y')
    stars.push({
      key: `sess:${sess.id}`,
      name: sess.name || 'session',
      kind: 'session',
      hx: 0.14 + s1 * 0.72,
      hy: 0.16 + s2 * 0.68,
      r: clamp(3 + (sess.agents?.length || 1) * 0.9, 3, 9),
      glow: 1,
      live: true,
      phase: s2 * Math.PI * 2,
      drift: 0.8 + s1,
    })
  }
  return stars
}

export function Firmament({
  orgs,
  sessions,
  handoffs,
  theme,
  height = 460,
}: {
  orgs: OrgSummary[]
  sessions: OrchestraSession[]
  handoffs: OrchestraHandoff[]
  theme: Theme
  height?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const hoverRef = useRef<{ x: number; y: number } | null>(null)

  // Holds the latest derived data — written by the data effect, read by the RAF loop each frame.
  const dataRef = useRef<DataSnapshot>({
    stars: [],
    orgIndex: new Map<string, Star>(),
    handoffs: [],
    colors: {
      gold: '#c9a86a',
      ice: '#92b9cc',
      faint: '#5f5a50',
      text: '#ece5d8',
    },
  })

  // Allows the data effect to trigger an immediate repaint (useful for reduced-motion / static
  // frames and for the frame that follows each poll even while the RAF loop is running).
  const drawRef = useRef<(() => void) | null>(null)

  // ── Data effect ──────────────────────────────────────────────────────────────
  // Runs whenever the polled data or the active theme changes.
  // ONLY recomputes derived values and stores them in dataRef — NO canvas setup, NO RAF, NO
  // listeners.  The running loop will pick up the new snapshot on its very next frame.
  useEffect(() => {
    const stars = buildStars(orgs, sessions)
    const orgIndex = new Map<string, Star>()
    for (const s of stars) if (s.kind === 'org') orgIndex.set(s.name, s)
    const colors = readColors()

    dataRef.current = { stars, orgIndex, handoffs, colors }

    // Trigger an immediate repaint so the post-poll frame and reduced-motion static view are
    // always up to date even though the RAF loop is not restarted.
    drawRef.current?.()
  }, [orgs, sessions, handoffs, theme])

  // ── Setup / animation effect ─────────────────────────────────────────────────
  // Mounts ONCE (deps: [height]).  Owns the canvas bootstrap, event listeners, and the RAF loop.
  // `t` is a closure variable here and survives across polls — no more stutter/jump on data refresh.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let raf = 0
    let t = 0
    let w = 0
    let h = 0
    let dpr = 1

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = rect.width
      h = rect.height
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // Window resize does not change the theme; colors in dataRef.current are refreshed by the
      // data effect whenever the theme prop changes, so no need to re-read them here.
    }

    const pos = (star: Star) => {
      const wobble = reduce ? 0 : 1
      const dx = Math.cos(t * 0.16 * star.drift + star.phase) * 10 * wobble
      const dy = Math.sin(t * 0.13 * star.drift + star.phase) * 9 * wobble
      return { x: star.hx * w + dx, y: star.hy * h + dy }
    }

    const draw = () => {
      // Always read from the ref so each frame paints the latest polled snapshot.
      const { stars, orgIndex, handoffs, colors } = dataRef.current

      ctx.clearRect(0, 0, w, h)
      const pts = stars.map((s) => ({ s, ...pos(s) }))

      // 近接の星座線（gossamer）
      ctx.lineWidth = 1
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i]
          const b = pts[j]
          const dist = Math.hypot(a.x - b.x, a.y - b.y)
          const max = Math.min(w, h) * 0.32
          if (dist < max) {
            const alpha = (1 - dist / max) * 0.16
            ctx.strokeStyle = hexA(colors.faint, alpha)
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }

      // handoff 線（金の脈絡：source→target）
      ctx.lineWidth = 1.2
      for (const ho of handoffs) {
        const a = orgIndex.get(ho.source)
        const b = orgIndex.get(ho.target)
        if (!a || !b) continue
        const pa = pos(a)
        const pb = pos(b)
        const pending = ho.status === 'pending'
        ctx.strokeStyle = hexA(colors.gold, pending ? 0.5 : 0.22)
        ctx.beginPath()
        ctx.moveTo(pa.x, pa.y)
        const mx = (pa.x + pb.x) / 2
        const my = (pa.y + pb.y) / 2 - 26
        ctx.quadraticCurveTo(mx, my, pb.x, pb.y)
        ctx.stroke()
      }

      // 星
      for (const p of pts) {
        const { s } = p
        const twinkle = reduce ? 1 : 0.7 + 0.3 * Math.sin(t * 1.6 * s.drift + s.phase)
        const color = s.kind === 'session' ? colors.ice : colors.gold
        const radius = s.r * (s.kind === 'session' ? 1 + 0.25 * Math.sin(t * 3 + s.phase) : 1)

        // ハロー
        const grd = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius * 6)
        grd.addColorStop(0, hexA(color, 0.42 * s.glow * twinkle))
        grd.addColorStop(1, hexA(color, 0))
        ctx.fillStyle = grd
        ctx.beginPath()
        ctx.arc(p.x, p.y, radius * 6, 0, Math.PI * 2)
        ctx.fill()

        // コア
        ctx.fillStyle = hexA(color, 0.9 * twinkle)
        ctx.beginPath()
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
        ctx.fill()

        if (s.live) {
          ctx.strokeStyle = hexA(color, 0.5)
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.arc(p.x, p.y, radius + 4 + (reduce ? 0 : 2 * Math.sin(t * 2 + s.phase)), 0, Math.PI * 2)
          ctx.stroke()
        }
      }

      // ホバー：最寄りの星にラベル
      const hover = hoverRef.current
      if (hover) {
        let best: { p: (typeof pts)[number]; d: number } | null = null
        for (const p of pts) {
          const d = Math.hypot(p.x - hover.x, p.y - hover.y)
          if (!best || d < best.d) best = { p, d }
        }
        if (best && best.d < 40) {
          const { p } = best
          ctx.fillStyle = colors.text
          ctx.font =
            "11px ui-monospace, 'SF Mono', 'Cascadia Code', monospace"
          ctx.textBaseline = 'middle'
          const label = p.s.name.length > 28 ? p.s.name.slice(0, 27) + '…' : p.s.name
          ctx.fillText(label.toUpperCase(), p.x + p.s.r + 10, p.y)
        }
      }
    }

    const loop = () => {
      t += 0.016
      draw()
      raf = requestAnimationFrame(loop)
    }

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      hoverRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }
    const onLeave = () => {
      hoverRef.current = null
    }

    resize()
    // Expose draw so the data effect can trigger immediate repaints.
    drawRef.current = draw
    if (reduce) {
      draw()
    } else {
      raf = requestAnimationFrame(loop)
    }
    window.addEventListener('resize', resize)
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseleave', onLeave)

    return () => {
      drawRef.current = null
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseleave', onLeave)
    }
  }, [height])

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="Pantheon Firmament — 組織と稼働セッションの星座図"
      style={{ width: '100%', height, display: 'block' }}
    />
  )
}

// "#rrggbb" + alpha → rgba()。CSS 変数が hex 前提（theme.css）。
function hexA(hex: string, alpha: number): string {
  const m = hex.replace('#', '')
  if (m.length < 6) return hex
  const r = parseInt(m.slice(0, 2), 16)
  const g = parseInt(m.slice(2, 4), 16)
  const b = parseInt(m.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${clamp(alpha, 0, 1)})`
}
