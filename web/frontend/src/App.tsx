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
  Map as MapIcon,
  Menu,
  Moon,
  Search,
  Settings,
  Sparkles,
  Sun,
  Boxes,
  KanbanSquare,
  ArrowRightLeft,
  CalendarClock,
  Inbox,
  Coins,
  PenSquare,
  Plug,
  Blocks,
  UserCheck,
} from 'lucide-react'
import { NavLink, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import { Toaster, toast } from 'sonner'

import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { AgentsPage } from '@/pages/AgentsPage'
import { AtlasPage } from '@/pages/AtlasPage'
import { ConnectionsPage } from '@/pages/ConnectionsPage'
import { DataPage } from '@/pages/DataPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { HandoffsPage } from '@/pages/HandoffsPage'
import { HelpPage } from '@/pages/HelpPage'
import { HumanTasksPage } from '@/pages/HumanTasksPage'
import { InboxPage } from '@/pages/InboxPage'
import { MarketplacePage } from '@/pages/MarketplacePage'
import { NotificationsPage } from '@/pages/NotificationsPage'
import { OnboardingPage } from '@/pages/OnboardingPage'
import { RevenuePage } from '@/pages/RevenuePage'
import { StudioPage } from '@/pages/StudioPage'
import { BoardPage } from '@/pages/BoardPage'
import { ContentSchedulePage } from '@/pages/ContentSchedulePage'
import { OrgsPage } from '@/pages/OrgsPage'
import { ProposalsPage } from '@/pages/ProposalsPage'
import { SessionsPage } from '@/pages/SessionsPage'
import { SettingsPage } from '@/pages/SettingsPage'

type NavItem = {
  to: string
  label: string
  icon: typeof LayoutDashboard
}

type NavGroup = {
  label: string
  items: NavItem[]
}

type SearchResult = {
  id: string
  type: string
  title: string
  subtitle: string
  route: string
  org_name?: string | null
  status?: string | null
}

// ナビは「ラベル付きグループ」の配列（C004）。20項目フラットを5グループに再編し、
// グループ内は使用頻度/ワークフロー順。日常導線（ダッシュボード/要対応/収益化）を上位に、
// 低頻度の開発者/設定系を末尾「システム」グループへ降格する。
const navGroups: NavGroup[] = [
  {
    label: 'はじめに',
    items: [
      { to: '/dashboard', label: 'ダッシュボード', icon: LayoutDashboard },
      { to: '/onboarding', label: '初回セットアップ', icon: Sparkles },
    ],
  },
  {
    label: '要対応',
    items: [
      { to: '/inbox', label: '承認インボックス', icon: Inbox },
      { to: '/human-tasks', label: 'あなたのタスク', icon: UserCheck },
      { to: '/notifications', label: '通知センター', icon: Bell },
    ],
  },
  {
    label: '組織と提案',
    items: [
      { to: '/orgs', label: '組織', icon: Building2 },
      { to: '/proposals', label: '改善提案', icon: Lightbulb },
      { to: '/agents', label: 'エージェント', icon: Bot },
    ],
  },
  {
    label: '収益化',
    items: [
      { to: '/studio', label: 'スタジオ', icon: PenSquare },
      { to: '/content', label: 'コンテンツ予約', icon: CalendarClock },
      { to: '/handoffs', label: '引き渡し', icon: ArrowRightLeft },
      { to: '/revenue', label: '収益', icon: Coins },
    ],
  },
  {
    label: 'システム / 高度な設定',
    items: [
      { to: '/connections', label: '連携設定', icon: Plug },
      { to: '/marketplace', label: 'マーケットプレイス', icon: Blocks },
      { to: '/atlas', label: 'Atlas', icon: MapIcon },
      { to: '/sessions', label: 'セッション', icon: Boxes },
      { to: '/board', label: '作業ボード', icon: KanbanSquare },
      { to: '/data', label: 'データ管理', icon: Database },
      { to: '/settings', label: '設定', icon: Settings },
      { to: '/help', label: 'ヘルプ', icon: HelpCircle },
    ],
  },
]

const THEME_STORAGE_KEY = 'pantheon-theme'
const SIDEBAR_STORAGE_KEY = 'pantheon-sidebar-collapsed'

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

function resultTypeLabel(type: string) {
  if (type === 'organization') return '組織'
  if (type === 'agent') return 'エージェント'
  if (type === 'proposal') return '提案'
  if (type === 'goal') return 'ゴール'
  return '検索結果'
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
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchLoading, setSearchLoading] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [env, setEnv] = useState<{ environment: string; env_label: string } | null>(null)
  const searchRef = useRef<HTMLDivElement | null>(null)
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

  // 本番(PROD)/開発(DEV) 環境を取得してバッジ表示＋DEV はアクセント帯を出す（取り違え防止）。
  useEffect(() => {
    let alive = true
    api<{ environment?: string; env_label?: string }>('GET', '/api/platform/status')
      .then((status) => {
        if (!alive) return
        const resolved = {
          environment: status.environment ?? 'production',
          env_label: status.env_label ?? 'PROD',
        }
        setEnv(resolved)
        if (typeof document !== 'undefined') {
          document.body.dataset.env = resolved.environment
        }
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setSearchOpen(false)
      }
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [])

  useEffect(() => {
    const query = searchQuery.trim()
    if (query.length < 2) {
      setSearchResults([])
      setSearchLoading(false)
      setSearchOpen(false)
      return undefined
    }

    setSearchLoading(true)
    const timer = window.setTimeout(async () => {
      try {
        const results = await api<SearchResult[]>('GET', `/api/search?q=${encodeURIComponent(query)}&limit=12`)
        setSearchResults(results)
        setSearchOpen(true)
      } catch {
        setSearchResults([])
      } finally {
        setSearchLoading(false)
      }
    }, 180)

    return () => window.clearTimeout(timer)
  }, [searchQuery])

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

  const handleSelectResult = (result: SearchResult) => {
    navigate(result.route)
    setSearchQuery('')
    setSearchResults([])
    setSearchOpen(false)
    setMobileOpen(false)
  }

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
                Pantheon <span>AI</span>
              </div>
            )}
          </div>

          <nav className="sidebar-nav" aria-label="メインナビゲーション">
            {navGroups.map((group, groupIndex) => {
              const iconOnly = collapsed && !mobileView
              return (
                <div className="sidebar-group" key={group.label} role="group" aria-label={group.label}>
                  {iconOnly ? (
                    groupIndex > 0 ? <div className="sidebar-group-divider" aria-hidden="true" /> : null
                  ) : (
                    <div className="sidebar-section-label">{group.label}</div>
                  )}
                  {group.items.map((item) => {
                    const Icon = item.icon
                    return (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) => cn('sidebar-item', isActive && 'active')}
                        aria-label={item.label}
                        title={item.label}
                        onClick={() => setMobileOpen(false)}
                      >
                        <Icon className="sidebar-item-icon" aria-hidden="true" />
                        {iconOnly ? null : <span className="sidebar-item-label">{item.label}</span>}
                      </NavLink>
                    )
                  })}
                </div>
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
              {collapsed && !mobileView ? null : <span className="sidebar-item-label">折りたたむ</span>}
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

              <div className="workspace-search" ref={searchRef}>
                <Search className="workspace-search-icon" size={15} aria-hidden="true" />
                <input
                  className="workspace-search-input"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onFocus={() => {
                    if (searchResults.length > 0) {
                      setSearchOpen(true)
                    }
                  }}
                  placeholder="組織・エージェント・提案・ゴールを検索"
                  aria-label="全体検索"
                />
                {searchLoading ? <span className="workspace-search-meta">検索中…</span> : null}
                {searchOpen ? (
                  <div className="search-dropdown" role="listbox" aria-label="検索結果">
                    {searchResults.length === 0 ? (
                      <div className="search-empty">一致する結果がありません。</div>
                    ) : (
                      searchResults.map((result) => (
                        <button
                          key={result.id}
                          type="button"
                          className="search-result"
                          onClick={() => handleSelectResult(result)}
                        >
                          <span className="badge badge-neutral">{resultTypeLabel(result.type)}</span>
                          <div className="search-result-body">
                            <div className="search-result-title">{result.title}</div>
                            <div className="search-result-subtitle">{result.subtitle || result.org_name || '—'}</div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="workspace-toolbar-actions">
              {env ? (
                <span
                  className={cn('env-badge', env.environment)}
                  title={`環境: ${env.environment === 'development' ? '開発 (DEV)' : '本番 (PROD)'}`}
                >
                  {env.env_label}
                </span>
              ) : null}

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
                            <div className="notification-item-subtitle">{event.details || event.org_name || 'Pantheon'}</div>
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
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/human-tasks" element={<HumanTasksPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/orgs" element={<OrgsPage />} />
        <Route path="/marketplace" element={<MarketplacePage />} />
        <Route path="/proposals" element={<ProposalsPage />} />
        <Route path="/handoffs" element={<HandoffsPage />} />
        <Route path="/studio" element={<StudioPage />} />
        <Route path="/content" element={<ContentSchedulePage />} />
        <Route path="/revenue" element={<RevenuePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/atlas" element={<AtlasPage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/board" element={<BoardPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}
