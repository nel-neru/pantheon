import { useMemo, useState } from 'react'
import { FileText, PenSquare, Twitter } from 'lucide-react'

import { countChars, readingStats, splitIntoThread, X_LIMIT } from '@/lib/contentFormat'

type Platform = 'x' | 'note' | 'wordpress'

const PLATFORM_TABS: { value: Platform; label: string; icon: typeof FileText }[] = [
  { value: 'x', label: 'X (Twitter)', icon: Twitter },
  { value: 'note', label: 'note', icon: FileText },
  { value: 'wordpress', label: 'WordPress', icon: FileText },
]

function XPreview({ body }: { body: string }) {
  const count = countChars(body)
  const over = count > X_LIMIT
  const thread = useMemo(() => splitIntoThread(body), [body])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className={`badge ${over ? 'badge-red' : 'badge-green'}`}>
          {count} / {X_LIMIT}
        </span>
        {over ? (
          <span className="text-sm text-muted">
            上限超過 → 自動で {thread.length} 件のスレッドに分割します
          </span>
        ) : (
          <span className="text-sm text-muted">1 ツイートに収まります</span>
        )}
      </div>
      {thread.length === 0 ? (
        <div className="text-muted text-sm">本文を入力するとプレビューが表示されます。</div>
      ) : (
        <div className="flex flex-col gap-2">
          {thread.map((tweet, index) => (
            <div key={index} className="rounded-xl border border-white/10 p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted">ツイート {index + 1}</span>
                <span className="text-xs text-muted">{countChars(tweet)} 字</span>
              </div>
              <div className="whitespace-pre-wrap text-sm">{tweet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ArticlePreview({ title, body, platform }: { title: string; body: string; platform: Platform }) {
  const stats = readingStats(body)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="badge badge-neutral">{stats.chars} 字</span>
        <span className="badge badge-neutral">{stats.lines} 行</span>
        <span className="badge badge-blue">約 {stats.minutes} 分で読了</span>
        {platform === 'wordpress' ? <span className="badge badge-neutral">WordPress 記事</span> : null}
      </div>
      <article className="rounded-xl border border-white/10 p-4 flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{title || '(タイトル未設定)'}</h2>
        {body.trim() ? (
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
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')

  return (
    <>
      <header className="page-header">
        <div className="page-title">
          <PenSquare size={20} /> コンテンツ・スタジオ
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <p className="text-sm text-muted">
          下書きを媒体ごとの形で確認できます。X は文字数と自動スレッド分割、note / WordPress は
          記事プレビューと読了目安を表示します（このページは下書き確認用で、外部投稿はしません）。
        </p>

        <div className="flex items-center gap-2 flex-wrap">
          {PLATFORM_TABS.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.value}
                type="button"
                className={`btn btn-sm ${platform === tab.value ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setPlatform(tab.value)}
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
                  <label className="input-label" htmlFor="studio-title">タイトル</label>
                  <input
                    id="studio-title"
                    className="input"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="記事タイトル"
                  />
                </div>
              ) : null}
              <div className="input-group">
                <label className="input-label" htmlFor="studio-body">本文</label>
                <textarea
                  id="studio-body"
                  className="input"
                  rows={16}
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder={platform === 'x' ? '投稿本文（280字を超えると自動でスレッドに分割）' : '記事本文'}
                />
              </div>
            </div>
          </div>

          <div className="card">
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
