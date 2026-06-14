import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Bell,
  Bot,
  Building2,
  ChevronLeft,
  ChevronRight,
  Database,
  HelpCircle,
  LayoutDashboard,
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
} from 'lucide-react'
import { NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Toaster, toast } from 'sonner'

import { AuthTokenDialog } from '@/components/AuthTokenDialog'
import { usePlatformUpdates } from '@/hooks/usePlatformUpdates'
import { api } from '@/lib/api'
import { levelBadge, levelLabel } from '@/lib/labels'
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

// 通知センターから返される個別の通知アイテム形状（/api/notifications レスポンス）。
type NotificationItem = {
  id: string
  level: string
  message: string
  org_name?: string | null
  created_at?: string | null
  read: boolean
  route?: string | null
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
    // 承認系は /inbox に集約（提案/引き渡し/投稿待ち/あなたのタスクを単一の対応ハブへ・C006）。
    // 通知はツールバーのベルが担うため通知センターはナビから外す（C007）。
    label: '要対応',
    items: [{ to: '/inbox', label: '承認インボックス', icon: Inbox }],
  },
  {
    label: '組織・エージェント',
    items: [
      { to: '/orgs', label: '組織', icon: Building2 },
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
  const location = useLocation()
  const mainRef = useRef<HTMLElement | null>(null)
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
  // C025: 検索候補のキーボード選択インデックス（-1 = 未選択）。
  const [searchActiveIndex, setSearchActiveIndex] = useState(-1)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [env, setEnv] = useState<{ environment: string; env_label: string } | null>(null)
  // C030: 既にオンボード済み（初期化済み＋組織あり）なら「初回セットアップ」をナビから隠す。
  const [onboarded, setOnboarded] = useState(false)
  // C007: 通知センターの実際の未読数とプレビューリスト。
  const [unreadCount, setUnreadCount] = useState(0)
  const [notificationItems, setNotificationItems] = useState<NotificationItem[]>([])
  const searchRef = useRef<HTMLDivElement | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  const notificationsRef = useRef<HTMLDivElement | null>(null)
  // C025: 通知ポップオーバーの先頭フォーカス用 ref。
  const notificationFirstItemRef = useRef<HTMLButtonElement | null>(null)
  const notifiedIds = useRef<Set<string>>(new Set())
  const { connected: updatesConnected, offline: updatesOffline, events } = usePlatformUpdates()

  // C007: 未読数を API から取得するユーティリティ。WS イベント受信後にも呼ぶ。
  const fetchUnreadCount = useCallback(() => {
    api<{ unread: number }>('GET', '/api/notifications/unread-count')
      .then((res) => setUnreadCount(res.unread))
      .catch(() => {})
  }, [])

  // C007: ポップオーバー用通知プレビュー（上限 8 件）を取得する。
  const fetchNotificationPreview = useCallback(() => {
    api<{ items: NotificationItem[]; unread: number }>('GET', '/api/notifications?limit=8')
      .then((res) => {
        setNotificationItems(res.items)
        setUnreadCount(res.unread)
      })
      .catch(() => {})
  }, [])

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

  // ルート遷移時にメイン領域を先頭へスクロールしフォーカスを移す（C041・キーボード/SR配慮）。
  useEffect(() => {
    const main = mainRef.current
    if (!main) return
    main.scrollTo?.({ top: 0 })
    main.focus({ preventScroll: true })
  }, [location.pathname])

  // 本番(PROD)/開発(DEV) 環境を取得してバッジ表示＋DEV はアクセント帯を出す（取り違え防止）。
  useEffect(() => {
    let alive = true
    api<{
      environment?: string
      env_label?: string
      initialized?: boolean
      total_organizations?: number
    }>('GET', '/api/platform/status')
      .then((status) => {
        if (!alive) return
        const resolved = {
          environment: status.environment ?? 'production',
          env_label: status.env_label ?? 'PROD',
        }
        setEnv(resolved)
        setOnboarded(Boolean(status.initialized) && (status.total_organizations ?? 0) > 0)
        if (typeof document !== 'undefined') {
          document.body.dataset.env = resolved.environment
        }
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  // C007: 初回マウント時に未読数を取得する。
  useEffect(() => {
    fetchUnreadCount()
  }, [fetchUnreadCount])

  // C025: ポップオーバー外クリックで検索/通知を閉じる。
  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setSearchOpen(false)
        setSearchActiveIndex(-1)
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
      setSearchActiveIndex(-1)
      return undefined
    }

    setSearchLoading(true)
    const timer = window.setTimeout(async () => {
      try {
        const results = await api<SearchResult[]>('GET', `/api/search?q=${encodeURIComponent(query)}&limit=12`)
        setSearchResults(results)
        setSearchOpen(true)
        setSearchActiveIndex(-1)
      } catch {
        setSearchResults([])
      } finally {
        setSearchLoading(false)
      }
    }, 180)

    return () => window.clearTimeout(timer)
  }, [searchQuery])

  // C007: WS イベントはトースト専用。受信後に未読数を再取得してバッジを更新する。
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
      // WS 受信をきっかけに未読数バッジを再取得（C007）。
      fetchUnreadCount()
    }
  }, [events, fetchUnreadCount])

  // C025: Ctrl/Cmd+K で検索欄へフォーカス。
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // C025: 通知ポップオーバーが開いたら先頭アイテムへフォーカスを移す。
  useEffect(() => {
    if (notificationsOpen) {
      // 描画後に先頭へフォーカス（requestAnimationFrame で DOM 確定後）。
      const id = window.requestAnimationFrame(() => {
        notificationFirstItemRef.current?.focus()
      })
      return () => window.cancelAnimationFrame(id)
    }
    return undefined
  }, [notificationsOpen])

  const handleSelectResult = (result: SearchResult) => {
    navigate(result.route)
    setSearchQuery('')
    setSearchResults([])
    setSearchOpen(false)
    setSearchActiveIndex(-1)
    setMobileOpen(false)
  }

  // C025: 検索ドロップダウンのキーボードイベントハンドラ。
  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!searchOpen || searchResults.length === 0) {
      if (event.key === 'Escape') {
        setSearchOpen(false)
        setSearchActiveIndex(-1)
      }
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setSearchActiveIndex((prev) => (prev < searchResults.length - 1 ? prev + 1 : 0))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setSearchActiveIndex((prev) => (prev > 0 ? prev - 1 : searchResults.length - 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (searchActiveIndex >= 0 && searchActiveIndex < searchResults.length) {
        handleSelectResult(searchResults[searchActiveIndex])
      }
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setSearchOpen(false)
      setSearchActiveIndex(-1)
    }
  }

  // C025: 通知ポップオーバーの Escape ハンドラ。
  const handleNotificationsKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      setNotificationsOpen(false)
    }
  }

  const toggleSidebar = () => {
    if (mobileView) {
      setMobileOpen((current) => !current)
      return
    }
    setCollapsed((current) => !current)
  }

  // C030: オンボード済みなら「初回セットアップ」をナビから外す（一度きりの導線を恒久占有させない）。
  const visibleGroups = onboarded
    ? navGroups
        .map((group) => ({ ...group, items: group.items.filter((item) => item.to !== '/onboarding') }))
        .filter((group) => group.items.length > 0)
    : navGroups

  // C007: 通知を 1 件既読化しルートがあれば遷移する。
  const handleNotificationClick = async (item: NotificationItem) => {
    try {
      await api<{ ok: boolean; unread: number }>('POST', `/api/notifications/${item.id}/read`)
      setUnreadCount((prev) => Math.max(0, prev - (item.read ? 0 : 1)))
      setNotificationItems((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, read: true } : n))
      )
    } catch {
      // 既読化に失敗してもナビゲーションは続行する。
    }
    if (item.route) {
      navigate(item.route)
    }
    setNotificationsOpen(false)
  }

  // C007: 全件既読化。
  const handleReadAll = async () => {
    try {
      await api<{ ok: boolean; unread: number }>('POST', '/api/notifications/read-all')
      setUnreadCount(0)
      setNotificationItems((prev) => prev.map((n) => ({ ...n, read: true })))
    } catch {
      // サイレント失敗（バッジ不整合は次回ポップオーバー開時に補正）。
    }
  }

  // C007: ポップオーバーを開くとき最新のプレビューを取得する。
  const handleToggleNotifications = () => {
    setNotificationsOpen((current) => {
      const next = !current
      if (next) {
        fetchNotificationPreview()
      }
      return next
    })
  }

  // aria-activedescendant 用の ID ヘルパー。
  const searchOptionId = (index: number) => `search-option-${index}`

  // 検索ドロップダウンの ID（コンボボックス関係付けに使用）。
  const searchListboxId = 'search-listbox'

  // 通知ポップオーバー ID（aria-controls に使用）。
  const notificationPopoverId = 'notification-popover'

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
            {visibleGroups.map((group, groupIndex) => {
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

        <main className="main" ref={mainRef} tabIndex={-1}>
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

              {/* C025: コンボボックスパターン（role=combobox / listbox / option）。 */}
              <div className="workspace-search" ref={searchRef}>
                <Search className="workspace-search-icon" size={15} aria-hidden="true" />
                <input
                  ref={searchInputRef}
                  className="workspace-search-input"
                  role="combobox"
                  aria-label="全体検索"
                  aria-expanded={searchOpen}
                  aria-haspopup="listbox"
                  aria-controls={searchListboxId}
                  aria-autocomplete="list"
                  aria-activedescendant={
                    searchOpen && searchActiveIndex >= 0
                      ? searchOptionId(searchActiveIndex)
                      : undefined
                  }
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onFocus={() => {
                    if (searchResults.length > 0) {
                      setSearchOpen(true)
                    }
                  }}
                  onKeyDown={handleSearchKeyDown}
                  placeholder="組織・エージェント・提案・ゴールを検索 (Ctrl+K)"
                />
                {searchLoading ? <span className="workspace-search-meta">検索中…</span> : null}
                {searchOpen ? (
                  <div
                    id={searchListboxId}
                    className="search-dropdown"
                    role="listbox"
                    aria-label="検索結果"
                  >
                    {searchResults.length === 0 ? (
                      <div className="search-empty" role="option" aria-selected={false}>
                        一致する結果がありません。
                      </div>
                    ) : (
                      searchResults.map((result, index) => (
                        <button
                          key={result.id}
                          id={searchOptionId(index)}
                          type="button"
                          role="option"
                          aria-selected={index === searchActiveIndex}
                          className={cn('search-result', index === searchActiveIndex && 'search-result-active')}
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

              {/* C007/C025: ベルボタン（未読数は API 由来）＋通知ポップオーバー。 */}
              <div
                className="notification-shell"
                ref={notificationsRef}
                onKeyDown={handleNotificationsKeyDown}
              >
                <button
                  type="button"
                  className="btn btn-ghost btn-icon"
                  aria-label={`通知${unreadCount > 0 ? `（未読 ${unreadCount} 件）` : ''}を開く`}
                  aria-expanded={notificationsOpen}
                  aria-controls={notificationPopoverId}
                  aria-haspopup="dialog"
                  onClick={handleToggleNotifications}
                >
                  <Bell size={16} />
                  {unreadCount > 0 ? (
                    <span className="notification-count" aria-hidden="true">
                      {unreadCount}
                    </span>
                  ) : null}
                </button>
                {notificationsOpen ? (
                  <div
                    id={notificationPopoverId}
                    className="notification-popover"
                    role="dialog"
                    aria-label="通知"
                  >
                    <div className="notification-popover-header">
                      <span>通知</span>
                      {notificationItems.some((n) => !n.read) ? (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => void handleReadAll()}
                        >
                          すべて既読
                        </button>
                      ) : null}
                    </div>
                    {notificationItems.length === 0 ? (
                      <div className="notification-empty">新しい通知はありません。</div>
                    ) : (
                      notificationItems.map((item, index) => (
                        <button
                          key={item.id}
                          ref={index === 0 ? notificationFirstItemRef : undefined}
                          type="button"
                          className={cn('notification-item', !item.read && 'notification-item-unread')}
                          onClick={() => void handleNotificationClick(item)}
                        >
                          <span className={`badge ${levelBadge(item.level)}`}>
                            {levelLabel(item.level)}
                          </span>
                          <div className="notification-item-body">
                            <div className="notification-item-title">{item.message}</div>
                            <div className="notification-item-subtitle">{item.org_name || 'Pantheon'}</div>
                          </div>
                        </button>
                      ))
                    )}
                    <div className="notification-popover-footer">
                      <NavLink
                        to="/notifications"
                        className="notification-see-all"
                        onClick={() => setNotificationsOpen(false)}
                      >
                        すべて見る
                      </NavLink>
                    </div>
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
          {updatesOffline ? (
            <div className="offline-banner" role="status">
              オフライン — ライブ更新サーバーに接続できません。表示が古い可能性があります。
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>
      <Toaster theme={theme} position="bottom-right" richColors />
      <AuthTokenDialog />
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
