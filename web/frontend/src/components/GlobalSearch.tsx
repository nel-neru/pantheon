import { useEffect, useId, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/lib/api'

type SearchResult = {
  id: string
  type: string
  title: string
  subtitle: string
  route: string
  org_name?: string | null
  status?: string | null
}

function resultTypeLabel(type: string) {
  if (type === 'organization') return '組織'
  if (type === 'agent') return 'エージェント'
  if (type === 'proposal') return '提案'
  if (type === 'goal') return 'ゴール'
  return '検索結果'
}

/**
 * 全体検索ボックス（A11y: combobox/listbox ロール、↑↓/Enter/Esc キーボード操作、
 * aria-activedescendant でアクティブ候補を支援技術へ通知）。
 */
export function GlobalSearch({ onNavigate }: { onNavigate?: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const listboxId = useId()
  const optionId = (index: number) => `${listboxId}-opt-${index}`

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setResults([])
      setLoading(false)
      setOpen(false)
      setActiveIndex(-1)
      return undefined
    }
    setLoading(true)
    const timer = window.setTimeout(async () => {
      try {
        const found = await api<SearchResult[]>('GET', `/api/search?q=${encodeURIComponent(trimmed)}&limit=12`)
        setResults(found)
        setOpen(true)
        setActiveIndex(found.length > 0 ? 0 : -1)
      } catch {
        setResults([])
        setActiveIndex(-1)
      } finally {
        setLoading(false)
      }
    }, 180)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [])

  const select = (result: SearchResult) => {
    navigate(result.route)
    setQuery('')
    setResults([])
    setOpen(false)
    setActiveIndex(-1)
    onNavigate?.()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((current) => (current + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((current) => (current - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const target = results[activeIndex] ?? results[0]
      if (target) select(target)
    }
  }

  return (
    <div className="workspace-search" ref={containerRef}>
      <Search className="workspace-search-icon" size={15} aria-hidden="true" />
      <input
        className="workspace-search-input"
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        aria-autocomplete="list"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => {
          if (results.length > 0) setOpen(true)
        }}
        onKeyDown={handleKeyDown}
        placeholder="組織・エージェント・提案・ゴールを検索"
        aria-label="全体検索"
      />
      {loading ? <span className="workspace-search-meta">検索中…</span> : null}
      {open ? (
        <div className="search-dropdown" role="listbox" id={listboxId} aria-label="検索結果">
          {results.length === 0 ? (
            <div className="search-empty">一致する結果がありません。</div>
          ) : (
            results.map((result, index) => (
              <button
                key={result.id}
                type="button"
                role="option"
                id={optionId(index)}
                aria-selected={index === activeIndex}
                className={cnActive(index === activeIndex)}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(result)}
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
  )
}

function cnActive(active: boolean) {
  return active ? 'search-result active' : 'search-result'
}
