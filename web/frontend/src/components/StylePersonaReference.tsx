import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Palette, UserCircle } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import type { DesignStyle, Persona } from '@/lib/api'

// ─── Types ───────────────────────────────────────────────────────────────────

type LoadState = 'idle' | 'loading' | 'loaded' | 'error'

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * 利用可能なデザインスタイルとペルソナのコンパクトな読み取り専用リファレンスパネル。
 * 展開/折りたたみ可能。StudioPage やコンテンツ系ページにサイドバー的に埋め込む想定。
 */
export function StylePersonaReference() {
  const [open, setOpen] = useState(false)
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [styles, setStyles] = useState<DesignStyle[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])

  const load = useCallback(async () => {
    if (loadState === 'loading' || loadState === 'loaded') return
    setLoadState('loading')
    try {
      const [stylesRes, personasRes] = await Promise.all([
        api<DesignStyle[]>('GET', '/api/design-styles'),
        api<Persona[]>('GET', '/api/personas'),
      ])
      setStyles(Array.isArray(stylesRes) ? stylesRes : [])
      setPersonas(Array.isArray(personasRes) ? personasRes : [])
      setLoadState('loaded')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'スタイル/ペルソナの読み込みに失敗しました。')
      setLoadState('error')
    }
  }, [loadState])

  // Load when first opened
  useEffect(() => {
    if (open) {
      void load()
    }
  }, [open, load])

  return (
    <div className="card">
      <button
        type="button"
        className="card-body flex items-center justify-between gap-2 w-full text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 font-semibold text-sm">
          <Palette size={15} />
          利用可能なスタイル / ペルソナ
        </div>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div className="border-t border-white/10 px-4 pb-4 flex flex-col gap-4">
          {loadState === 'loading' ? (
            <div className="flex items-center gap-2 text-sm text-muted pt-3">
              <div className="spinner" />
              読み込み中…
            </div>
          ) : loadState === 'error' ? (
            <div className="text-sm text-muted pt-3">
              読み込みに失敗しました。
              <button
                type="button"
                className="btn btn-ghost btn-sm ml-2"
                onClick={() => {
                  setLoadState('idle')
                  void load()
                }}
              >
                再試行
              </button>
            </div>
          ) : (
            <>
              {/* デザインスタイル */}
              <div className="flex flex-col gap-2 pt-3">
                <div className="flex items-center gap-1 text-xs font-semibold text-muted uppercase tracking-wide">
                  <Palette size={12} />
                  デザインスタイル（{styles.length}）
                </div>
                {styles.length === 0 ? (
                  <div className="text-sm text-muted">スタイルがありません。</div>
                ) : (
                  <div className="flex flex-col gap-1">
                    {styles.map((s) => (
                      <div key={s.id} className="flex items-start gap-2 text-sm">
                        <span className="badge badge-neutral shrink-0 font-mono">{s.id}</span>
                        <div className="min-w-0">
                          <div className="font-medium">{s.name}</div>
                          {s.description ? (
                            <div className="text-xs text-muted">{s.description}</div>
                          ) : null}
                          {s.palette ? (
                            <div className="text-xs text-muted">パレット: {s.palette}</div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ペルソナ */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 text-xs font-semibold text-muted uppercase tracking-wide">
                  <UserCircle size={12} />
                  ペルソナ（{personas.length}）
                </div>
                {personas.length === 0 ? (
                  <div className="text-sm text-muted">ペルソナがありません。</div>
                ) : (
                  <div className="flex flex-col gap-1">
                    {personas.map((p) => (
                      <div key={p.id} className="flex items-start gap-2 text-sm">
                        <span className="badge badge-neutral shrink-0 font-mono">{p.id}</span>
                        <div className="min-w-0">
                          <div className="font-medium">{p.name}</div>
                          {p.role ? (
                            <div className="text-xs text-muted">{p.role}</div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
