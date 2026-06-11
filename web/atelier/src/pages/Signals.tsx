import { useState } from 'react'

import { Exhibit, EmptyState, ErrorNote, Loading, Plate, Tag } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { clamp, relativeTime } from '@/lib/format'
import type { Trend } from '@/lib/types'

const SOURCE_TONE: Record<string, 'gold' | 'ice' | 'green' | 'rose' | 'neutral'> = {
  web: 'ice',
  youtube: 'rose',
  rss: 'green',
}

function scoreIndex(score: number): number {
  // スコアは 0..1 想定。万一 1 超なら 100 上限に丸める。
  const v = score <= 1 ? score * 100 : score
  return Math.round(clamp(v, 0, 100))
}

export function Signals() {
  const trends = useApi<Trend[]>('/api/trends?limit=60', 60000)
  const [busy, setBusy] = useState<null | 'collect' | 'convert'>(null)
  const [note, setNote] = useState<string>('')

  const run = async (kind: 'collect' | 'convert') => {
    setBusy(kind)
    setNote('')
    try {
      const res = await api<Record<string, unknown>>(
        'POST',
        kind === 'collect' ? '/api/trends/collect' : '/api/trends/convert',
      )
      setNote(
        kind === 'collect'
          ? `収集完了: ${JSON.stringify(res)}`
          : `変換完了: ${JSON.stringify(res)}`,
      )
      trends.refetch()
    } catch (e) {
      setNote(`失敗: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  const items = (trends.data ?? []).slice().sort((a, b) => b.score - a.score)
  const [lead, ...rest] = items

  return (
    <>
      <Exhibit
        index={4}
        kicker="The Signals"
        title={
          <>
            風を、<em>読む。</em>
          </>
        }
        lede="Web・RSS・YouTube から集めた潮流を、スコア順に組んだ号外。高スコアの兆しは、承認ゲートを通って次の一手（記事・新規事業）に変わります。"
        actions={
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-gold" disabled={busy !== null} onClick={() => run('collect')}>
              {busy === 'collect' ? '収集中…' : '今すぐ収集'}
            </button>
            <button type="button" className="btn" disabled={busy !== null} onClick={() => run('convert')}>
              {busy === 'convert' ? '変換中…' : '提案へ変換'}
            </button>
          </div>
        }
      />

      {note ? (
        <div className="mb-6 mono text-[11px] tracking-wide text-dim break-all">{note}</div>
      ) : null}

      {trends.loading && !trends.data ? <Loading label="潮流を集める" /> : null}
      {trends.error && !trends.data ? <ErrorNote message={trends.error} /> : null}
      {trends.data && items.length === 0 ? (
        <EmptyState title="まだ兆しはありません" hint="「今すぐ収集」で最新トレンドを取り込みます" />
      ) : null}

      {lead ? <Lead trend={lead} /> : null}

      <div className="mt-10 gallery-grid grid grid-cols-1 md:grid-cols-2">
        {rest.map((t) => (
          <TrendRow key={t.hash || t.url} trend={t} />
        ))}
      </div>
    </>
  )
}

function Lead({ trend }: { trend: Trend }) {
  return (
    <Plate no="LEAD" className="rise">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr] md:items-center">
        <div className="flex flex-col items-start">
          <span className="kicker mb-1">index</span>
          <span className="figure-stat text-gold">{scoreIndex(trend.score)}</span>
        </div>
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Tag tone={SOURCE_TONE[trend.source] ?? 'neutral'}>{trend.source || 'web'}</Tag>
            {trend.genre ? <Tag tone="gold">{trend.genre}</Tag> : null}
            <span className="mono text-faint text-[10px] tracking-wide">
              {relativeTime(trend.collected_at)}
            </span>
          </div>
          <a href={trend.url} target="_blank" rel="noreferrer" className="block">
            <h2 className="serif text-3xl leading-tight hover:text-gold transition-colors">
              {trend.title || '(無題)'}
            </h2>
          </a>
          <p className="text-dim mt-3 text-sm line-clamp-3">{trend.summary}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {(trend.topics ?? []).slice(0, 6).map((tp) => (
              <span key={tp} className="mono text-faint text-[10px] tracking-wider">
                #{tp}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Plate>
  )
}

function TrendRow({ trend }: { trend: Trend }) {
  return (
    <a
      href={trend.url}
      target="_blank"
      rel="noreferrer"
      className="block p-6 transition-colors hover:bg-[color:var(--ink-2)]"
    >
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-center gap-2">
          <Tag tone={SOURCE_TONE[trend.source] ?? 'neutral'}>{trend.source || 'web'}</Tag>
          <span className="mono text-faint text-[10px] tracking-wide">
            {relativeTime(trend.collected_at)}
          </span>
        </div>
        <span className="numeral text-2xl text-gold">{scoreIndex(trend.score)}</span>
      </div>
      <h3 className="serif mt-3 text-xl leading-snug line-clamp-2">{trend.title || '(無題)'}</h3>
      <p className="text-dim mt-2 text-sm line-clamp-2">{trend.summary}</p>
    </a>
  )
}
