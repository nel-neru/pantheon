import { useEffect, useState } from 'react'
import {
  Bot,
  Building2,
  ChevronLeft,
  ChevronRight,
  Database,
  HelpCircle,
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  Search,
  Settings,
  Target,
} from 'lucide-react'
import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'

import { cn } from '@/lib/utils'
import { AgentsPage } from '@/pages/AgentsPage'
import { AnalyzePage } from '@/pages/AnalyzePage'
import { ChatPage } from '@/pages/ChatPage'
import { DataPage } from '@/pages/DataPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { GoalsPage } from '@/pages/GoalsPage'
import { HelpPage } from '@/pages/HelpPage'
import { OrgsPage } from '@/pages/OrgsPage'
import { ProposalsPage } from '@/pages/ProposalsPage'
import { SettingsPage } from '@/pages/SettingsPage'

type NavItem = {
  to: string
  label: string
  icon: typeof MessageSquare
}

const navItems: NavItem[] = [
  { to: '/chat', label: 'チャット', icon: MessageSquare },
  { to: '/orgs', label: '組織', icon: Building2 },
  { to: '/analyze', label: '分析', icon: Search },
  { to: '/goals', label: 'ゴール', icon: Target },
  { to: '/proposals', label: '改善提案', icon: Lightbulb },
  { to: '/agents', label: 'エージェント', icon: Bot },
  { to: '/dashboard', label: 'プラットフォーム', icon: LayoutDashboard },
  { to: '/data', label: 'データ管理', icon: Database },
  { to: '/settings', label: '設定', icon: Settings },
  { to: '/help', label: 'ヘルプ', icon: HelpCircle },
]

function LogoMark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="sidebar-logo">
      <rect x="2" y="2" width="8" height="8" rx="2" fill="currentColor" opacity="0.45" />
      <rect x="14" y="2" width="8" height="8" rx="2" fill="currentColor" opacity="0.9" />
      <rect x="2" y="14" width="8" height="8" rx="2" fill="currentColor" opacity="0.75" />
      <rect x="14" y="14" width="8" height="8" rx="2" fill="currentColor" />
    </svg>
  )
}

function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(max-width: 768px)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const media = window.matchMedia('(max-width: 768px)')
    const update = (event?: MediaQueryListEvent) => {
      setCollapsed(event ? event.matches : media.matches)
    }

    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return (
    <div className="layout">
      <aside className={cn('sidebar', collapsed && 'collapsed')}>
        <div className="sidebar-header">
          <LogoMark />
          {!collapsed ? (
            <div className="sidebar-brand">
              RepoCorp <span>AI</span>
            </div>
          ) : null}
        </div>

        <nav className="sidebar-nav" aria-label="メインナビゲーション">
          {!collapsed ? <div className="sidebar-section-label">ワークスペース</div> : null}
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => cn('sidebar-item', isActive && 'active')}
              >
                <Icon className="sidebar-item-icon" />
                {!collapsed ? <span className="sidebar-item-label">{item.label}</span> : null}
              </NavLink>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            className="sidebar-item"
            onClick={() => setCollapsed((current) => !current)}
            aria-label={collapsed ? 'サイドバーを展開' : 'サイドバーを折りたたむ'}
          >
            {collapsed ? (
              <ChevronRight className="sidebar-item-icon" />
            ) : (
              <ChevronLeft className="sidebar-item-icon" />
            )}
            {!collapsed ? <span className="sidebar-item-label">折りたたむ</span> : null}
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/orgs" element={<OrgsPage />} />
          <Route path="/proposals" element={<ProposalsPage />} />
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/goals" element={<GoalsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
      <Toaster theme="dark" position="bottom-right" />
    </>
  )
}
