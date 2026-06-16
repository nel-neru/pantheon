import { NavLink, Outlet } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { ThemeProvider, useThemeCtx } from '@/hooks/useThemeContext'
import { LiveProvider, useLive } from '@/hooks/useLiveContext'
import { ClaudeStatusBanner } from './ClaudeStatusBanner'
import {
  AtelierIcon,
  HandbookIcon,
  InboxIcon,
  LabIcon,
  MoonIcon,
  ObservatoryIcon,
  PantheonIcon,
  PantheonMark,
  SignalsIcon,
  SunIcon,
} from './Icon'

type Nav = { to: string; label: string; Icon: typeof ObservatoryIcon }

const NAV: Nav[] = [
  { to: '/', label: 'Observatory', Icon: ObservatoryIcon },
  { to: '/pantheon', label: 'Pantheon', Icon: PantheonIcon },
  { to: '/atelier', label: 'Atelier', Icon: AtelierIcon },
  { to: '/signals', label: 'Signals', Icon: SignalsIcon },
  { to: '/inbox', label: 'Inbox', Icon: InboxIcon },
  { to: '/lab', label: 'Lab', Icon: LabIcon },
  { to: '/handbook', label: 'Handbook', Icon: HandbookIcon },
]

function Rail() {
  return (
    <nav className="rail" aria-label="主ナビゲーション">
      <div className="rail-mark" aria-hidden="true">
        <PantheonMark />
      </div>
      {NAV.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) => cn('rail-link', isActive && 'active')}
          aria-label={label}
        >
          <Icon size={22} />
          <span className="rail-tip">{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

function Masthead() {
  const { theme, toggle } = useThemeCtx()
  const { connected } = useLive()
  return (
    <div className="masthead">
      <div className="masthead-inner">
        <div className="wordmark">
          <b>Pantheon</b>
          <span>Atelier · Observatory</span>
        </div>
        <div className="flex items-center gap-5">
          <div
            className="flex items-center gap-2 mono text-[10px] tracking-[0.22em] uppercase"
            style={{ color: connected ? 'var(--ice)' : 'var(--text-faint)' }}
          >
            <span className={cn('dot', connected && 'dot-live')} />
            {connected ? 'Live' : 'Reconnecting'}
          </div>
          <button
            type="button"
            className="rail-link"
            style={{ width: 40, height: 40 }}
            onClick={toggle}
            aria-label={theme === 'nocturne' ? 'Daylight に切替' : 'Nocturne に切替'}
          >
            {theme === 'nocturne' ? <SunIcon size={18} /> : <MoonIcon size={18} />}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Shell() {
  return (
    <ThemeProvider>
      <LiveProvider>
        <div className="atelier-shell">
          <a href="#main" className="skip-link">
            本文へスキップ
          </a>
          <Rail />
          <div className="stage">
            <Masthead />
            <ClaudeStatusBanner />
            <main id="main" className="stage-inner">
              <Outlet />
            </main>
          </div>
        </div>
      </LiveProvider>
    </ThemeProvider>
  )
}
