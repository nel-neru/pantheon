import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  Bot,
  Building2,
  ChevronLeft,
  ChevronRight,
  Database,
  HelpCircle,
  LayoutDashboard,
  Lightbulb,
  Menu,
  MessageSquare,
  Moon,
  Search,
  Settings,
  Sun,
  Target,
  TerminalSquare,
} from 'lucide-react'
import { NavLink, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import { Toaster, toast } from 'sonner'

import { GlobalSearch } from '@/components/GlobalSearch'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
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
import { TerminalPage } from '@/pages/TerminalPage'

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
  { to: '/terminal', label: 'ターミナル', icon: TerminalSquare },
  { to: '/dashboard', label: 'プラットフォーム', icon: LayoutDashboard },
  { to: '/data', label: 'データ管理', icon: Database },
  { to: '/settings', label: '設定', icon: Settings },
  { to: '/help', label: 'ヘルプ', icon: HelpCircle },
]

const THEME_STORAGE_KEY = 'repocorp-theme'
const SIDEBAR_STORAGE_KEY = 'repocorp-sidebar-collapsed'

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
  const navigate = useNavigate()
  const [mobileView, setMobileView] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(max-width: 768px)').matches
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
  })
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window === 'undefined') return 'dark'
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return stored === 'light' ? 'light' : 'dark'
  })
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const notificationsRef = useRef<HTMLDivElement | null>(null)
  const notifiedIds = useRef<Set<string>>(new Set())
  const { connected: updatesConnected, events } = usePlatformUpdates()

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const media = window.matchMedia('(max-width: 768px)')
    const update = (event?: MediaQueryListEvent) => {
      const nextMobile = event ? event.matches : media.matches
      setMobileView(nextMobile)
      if (!nextMobile) {
        setMobileOpen(false)
      }
    }

    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || mobileView) return
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed))
  }, [collapsed, mobileView])

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.body.dataset.theme = theme
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [])

  useEffect(() => {
    for (const event of events.slice(0, 5).reverse()) {
      const eventId = event.id ?? `${event.type}-${event.timestamp}`
      if (!eventId || notifiedIds.current.has(eventId) || event.type === 'status') {
        continue
      }
      notifiedIds.current.add(eventId)
      const message = event.details || event.title || '新しい更新があります。'
      if (event.status === 'error') {
        toast.error(message)
      } else if (event.status === 'pending') {
        toast.info(message)
      } else {
        toast.success(message)
      }
    }
  }, [events])

  const visibleNotifications = useMemo(() => events.filter((event) => event.type !== 'status').slice(0, 8), [events])

  const toggleSidebar = () => {
    if (mobileView) {
      setMobileOpen((current) => !current)
      return
    }
    setCollapsed((current) => !current)
  }

  return (
    <>
      <div className={cn('layout', mobileOpen && 'nav-open')}>
        {mobileView && mobileOpen ? (
          <button
            type="button"
            className="mobile-nav-backdrop"
            aria-label="ナビゲーションを閉じる"
            onClick={() => setMobileOpen(false)}
          />
        ) : null}

        <aside className={cn('sidebar', collapsed && !mobileView && 'collapsed', mobileOpen && 'mobile-open')}>
          <div className="sidebar-header">
            <LogoMark />
            {collapsed && !mobileView ? null : (
              <div className="sidebar-brand">
                RepoCorp <span>AI</span>
              </div>
            )}
          </div>

          <nav className="sidebar-nav" aria-label="メインナビゲーション">
            {collapsed && !mobileView ? null : <div className="sidebar-section-label">ワークスペース</div>}
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => cn('sidebar-item', isActive && 'active')}
                  aria-label={item.label}
                  onClick={() => setMobileOpen(false)}
                >
                  <Icon className="sidebar-item-icon" aria-hidden="true" />
                  {collapsed && !mobileView ? null : <span className="sidebar-item-label">{item.label}</span>}
                </NavLink>
              )
            })}
          </nav>

          <div className="sidebar-footer">
            <button
              type="button"
              className="sidebar-item"
              onClick={toggleSidebar}
              aria-label={mobileView ? 'サイドバーを閉じる' : collapsed ? 'サイドバーを展開' : 'サイドバーを折りたたむ'}
            >
              {collapsed && !mobileView ? (
                <ChevronRight className="sidebar-item-icon" aria-hidden="true" />
              ) : (
                <ChevronLeft className="sidebar-item-icon" aria-hidden="true" />
              )}
              {collapsed && !mobileView ? null : <span className="sidebar-item-label">ナビゲーション</span>}
            </button>
          </div>
        </aside>

        <main className="main">
          <div className="workspace-toolbar">
            <div className="workspace-toolbar-left">
              <button
                type="button"
                className="btn btn-ghost btn-icon toolbar-mobile-toggle"
                onClick={() => setMobileOpen(true)}
                aria-label="ナビゲーションを開く"
              >
                <Menu size={16} />
              </button>

              <GlobalSearch onNavigate={() => setMobileOpen(false)} />
            </div>

            <div className="workspace-toolbar-actions">
              <div className={cn('live-status', updatesConnected ? 'connected' : 'connecting')}>
                <span className={cn('status-dot', updatesConnected ? 'connected' : 'connecting')} />
                {updatesConnected ? 'リアルタイム接続中' : '再接続中'}
              </div>

              <div className="notification-shell" ref={notificationsRef}>
                <button
                  type="button"
                  className="btn btn-ghost btn-icon"
                  aria-label="通知を開く"
                  onClick={() => setNotificationsOpen((current) => !current)}
                >
                  <Bell size={16} />
                  {visibleNotifications.length > 0 ? <span className="notification-count">{visibleNotifications.length}</span> : null}
                </button>
                {notificationsOpen ? (
                  <div className="notification-popover">
                    <div className="notification-popover-header">通知</div>
                    {visibleNotifications.length === 0 ? (
                      <div className="notification-empty">新しい通知はありません。</div>
                    ) : (
                      visibleNotifications.map((event, index) => (
                        <button
                          key={event.id ?? `${event.type}-${index}`}
                          type="button"
                          className="notification-item"
                          onClick={() => {
                            if (event.route) {
                              navigate(event.route)
                            }
                            setNotificationsOpen(false)
                          }}
                        >
                          <span className={`badge ${event.status === 'error' ? 'badge-red' : event.status === 'pending' ? 'badge-yellow' : 'badge-green'}`}>
                            {event.status === 'error' ? 'error' : event.status === 'pending' ? 'live' : 'done'}
                          </span>
                          <div className="notification-item-body">
                            <div className="notification-item-title">{event.title || '更新'}</div>
                            <div className="notification-item-subtitle">{event.details || event.org_name || 'RepoCorp AI'}</div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                ) : null}
              </div>

              <button
                type="button"
                className="btn btn-ghost btn-icon"
                onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
                aria-label={theme === 'dark' ? 'ライトテーマに切り替える' : 'ダークテーマに切り替える'}
              >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>
          </div>
          <Outlet />
        </main>
      </div>
      <Toaster theme={theme} position="bottom-right" richColors />
    </>
  )
}

export default function App() {
  return (
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
        <Route path="/terminal" element={<TerminalPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  )
}
