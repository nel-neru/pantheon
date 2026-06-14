import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Copy, FileText, PenSquare, Twitter } from 'lucide-react'
import { toast } from 'sonner'

import { countChars, readingStats, splitIntoThread, X_LIMIT } from '@/lib/contentFormat'
import { PageHeader } from '@/components/PageHeader'

type Platform = 'x' | 'note' | 'wordpress'

const PLATFORM_TABS: { value: Platform; label: string; icon: typeof FileText }[] = [
  { value: 'x', label: 'X (Twitter)', icon: Twitter },
  { value: 'note', label: 'note', icon: BookOpen },
  { value: 'wordpress', label: 'WordPress', icon: FileText },
]

const LS_KEY_TITLE = 'studio:title'
const LS_KEY_BODY = 'studio:body'

// ローカルストレージへの保存（デバウンス用）
function lsSave(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // クォータ超過などは握りつぶして画面を壊さない
  }
}

function lsLoad(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

async function copyText(text: string, successMsg = 'コピーしました') {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(successMsg)
  } catch {
    toast.error('クリップボードへのコピーに失敗しました。')
  }
}

function XPreview({ body }: { body: string }) {
  const thread = useMemo(() => splitIntoThread(body), [body])
  const count = countChars(body)
  // 閾値バグ修正: 1件に収まるかは thread.length で判定（count>X_LIMIT では接尾辞ぶん上限が
  // 縮む275〜280字帯で緑表示なのに2件分割になる嘘表示が起きるため）。
  const isMultiple = thread.length > 1

  const handleCopyAll = useCallback(async () => {
    const joined = thread.map((t, i) => `[${i + 1}/${thread.length}] ${t}`).join('\n\n')
    await copyText(joined, `全 ${thread.length} 件をコピーしました`)
  }, [thread])

  const handleCopyTweet = useCallback(async (tweet: string, index: number) => {
    await copyText(tweet, `ツイート ${index + 1} をコピーしました`)
  }, [])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          id="x-char-count-badge"
          className={`badge ${isMultiple ? 'badge-red' : 'badge-green'}`}
        >
          {count} / {X_LIMIT}
        </span>
        {isMultiple ? (
          <span id="x-thread-status-text" className="text-sm text-muted">
            上限超過 → 自動で {thread.length} 件のスレッドに分割します
          </span>
        ) : (
          <span id="x-thread-status-text" className="text-sm text-muted">
            1 ツイートに収まります
          </span>
        )}
        {thread.length > 0 && (
          <button
            type="button"
            className="btn btn-ghost btn-sm ml-auto"
            onClick={() => void handleCopyAll()}
            title="全ツイートをコピー（区切り付き）"
          >
            <Copy size={12} />
            全件コピー
          </button>
        )}
      </div>
      {thread.length === 0 ? (
        <div className="text-muted text-sm">本文を入力するとプレビューが表示されます。</div>
      ) : (
        <div id="x-tweet-card-list" className="flex flex-col gap-2">
          {thread.map((tweet, index) => (
            <div key={index} className="rounded-xl border border-white/10 p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted">ツイート {index + 1}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted">{countChars(tweet)} 字</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void handleCopyTweet(tweet, index)}
                    title="このツイートをコピー"
                  >
                    <Copy size={12} />
                    コピー
                  </button>
                </div>
              </div>
              <div className="whitespace-pre-wrap text-sm">{tweet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function countHeadings(text: string): number {
  return (text.match(/^#{1,6}\s/gm) ?? []).length
}

function ArticlePreview({
  title,
  body,
  platform,
}: {
  title: string
  body: string
  platform: Platform
}) {
  const stats = readingStats(body)
  const hasBody = body.trim().length > 0
  const headings = platform === 'wordpress' ? countHeadings(body) : null

  const handleCopy = useCallback(async () => {
    const parts: string[] = []
    if (title) parts.push(`# ${title}`)
    if (body) parts.push(body)
    await copyText(parts.join('\n\n'), 'タイトルと本文をコピーしました')
  }, [title, body])

  return (
    <div className="flex flex-col gap-3">
      {/* 空本文のときはバッジ群を非表示（空でも「約1分で読了」が出るのを防ぐ） */}
      {hasBody && (
        <div id="article-stats-badges" className="flex items-center gap-2 flex-wrap">
          <span className="badge badge-neutral">{stats.chars} 字</span>
          <span className="badge badge-neutral">{stats.lines} 行</span>
          <span className="badge badge-blue">約 {stats.minutes} 分で読了</span>
          {/* WordPress 記事バッジは自明なので削除。見出し数は差別化有用指標として表示 */}
          {headings !== null && headings > 0 ? (
            <span className="badge badge-neutral">見出し {headings} 個</span>
          ) : null}
        </div>
      )}
      <article
        id="article-preview-body"
        className="rounded-xl border border-white/10 p-4 flex flex-col gap-2"
      >
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{title || '(タイトル未設定)'}</h2>
          <button
            type="button"
            className="btn btn-ghost btn-sm shrink-0"
            onClick={() => void handleCopy()}
            title="タイトルと本文をコピー"
          >
            <Copy size={12} />
            コピー
          </button>
        </div>
        {hasBody ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{body}</div>
        ) : (
          <div className="text-muted text-sm">本文を入力するとプレビューが表示されます。</div>
        )}
      </article>
    </div>
  )
}

export function StudioPage() {
  const [platform, setPlatform] = useState<Platform>('x')
  // localStorage から初期値を復元する（永続化 — リロード・画面遷移後も下書きを維持）
  const [title, setTitle] = useState<string>(() => lsLoad(LS_KEY_TITLE))
  const [body, setBody] = useState<string>(() => lsLoad(LS_KEY_BODY))

  // デバウンスタイマー ref（毎キーストロークで保存は重いため 500ms 待つ）
  const titleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const bodyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleTitleChange = (value: string) => {
    setTitle(value)
    if (titleTimer.current) clearTimeout(titleTimer.current)
    titleTimer.current = setTimeout(() => lsSave(LS_KEY_TITLE, value), 500)
  }

  const handleBodyChange = (value: string) => {
    setBody(value)
    if (bodyTimer.current) clearTimeout(bodyTimer.current)
    bodyTimer.current = setTimeout(() => lsSave(LS_KEY_BODY, value), 500)
  }

  // アンマウント時にタイマーをクリア
  useEffect(() => {
    return () => {
      if (titleTimer.current) clearTimeout(titleTimer.current)
      if (bodyTimer.current) clearTimeout(bodyTimer.current)
    }
  }, [])

  return (
    <>
      <PageHeader
        title={
          <>
            <PenSquare size={20} /> コンテンツ・スタジオ
          </>
        }
      />

      <div className="page-content flex flex-col gap-4">
        <p className="text-sm text-muted">
          下書きを媒体ごとの形で確認できます。X は文字数と自動スレッド分割、note / WordPress は
          記事プレビューと読了目安を表示します（このページは下書き確認用で、外部投稿はしません）。
        </p>

        {/* タブ: role="tablist" + aria-selected でスクリーンリーダ/キーボード操作に対応 */}
        <div role="tablist" aria-label="投稿媒体" className="flex items-center gap-2 flex-wrap">
          {PLATFORM_TABS.map((tab) => {
            const Icon = tab.icon
            const isSelected = platform === tab.value
            return (
              <button
                key={tab.value}
                type="button"
                role="tab"
                id={`platform-tab-${tab.value}`}
                aria-selected={isSelected}
                aria-controls="studio-preview-panel"
                className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setPlatform(tab.value)}
                onKeyDown={(e) => {
                  // 左右キーでタブを移動（WAI-ARIA Tabs Pattern）
                  const tabs: Platform[] = ['x', 'note', 'wordpress']
                  const idx = tabs.indexOf(tab.value)
                  if (e.key === 'ArrowRight') {
                    setPlatform(tabs[(idx + 1) % tabs.length])
                  } else if (e.key === 'ArrowLeft') {
                    setPlatform(tabs[(idx + tabs.length - 1) % tabs.length])
                  }
                }}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            )
          })}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="card">
            <div className="card-body flex flex-col gap-3">
              <h2 className="card-title">下書き</h2>
              {platform !== 'x' ? (
                <div className="input-group">
                  <label className="input-label" htmlFor="studio-title-input">
                    タイトル
                  </label>
                  <input
                    id="studio-title-input"
                    className="input"
                    value={title}
                    onChange={(event) => handleTitleChange(event.target.value)}
                    placeholder="記事タイトル"
                  />
                </div>
              ) : null}
              <div className="input-group">
                <label className="input-label" htmlFor="studio-body-textarea">
                  本文
                </label>
                <textarea
                  id="studio-body-textarea"
                  className="input min-h-64"
                  value={body}
                  onChange={(event) => handleBodyChange(event.target.value)}
                  placeholder={
                    platform === 'x'
                      ? '投稿本文（280字を超えると自動でスレッドに分割）'
                      : '記事本文'
                  }
                />
              </div>
            </div>
          </div>

          <div
            id="studio-preview-panel"
            role="tabpanel"
            aria-labelledby={`platform-tab-${platform}`}
            className="card"
          >
            <div className="card-body flex flex-col gap-3">
              <h2 className="card-title">プレビュー</h2>
              {platform === 'x' ? (
                <XPreview body={body} />
              ) : (
                <ArticlePreview title={title} body={body} platform={platform} />
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
