import { Firmament } from '@/components/Firmament'
import { ArrowIcon } from '@/components/Icon'
import { Exhibit, ErrorNote, Loading, Plate, Stat, Tag } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { useLive } from '@/hooks/useLiveContext'
import { useThemeCtx } from '@/hooks/useThemeContext'
import { compactNumber, relativeTime } from '@/lib/format'
import type {
  DaemonsPayload,
  OrchestraData,
  OrgSummary,
  UsageSummary,
} from '@/lib/types'

const GOVERNOR_TONE: Record<string, 'green' | 'gold' | 'rose'> = {
  ok: 'green',
  soft_limit: 'gold',
  hard_limit: 'rose',
  rate_limited: 'rose',
}

export function Observatory() {
  const { theme } = useThemeCtx()
  const orchestra = useApi<OrchestraData>('/api/dashboard/orchestra', 8000)
  const orgs = useApi<OrgSummary[]>('/api/organizations', 30000)
  const usage = useApi<UsageSummary>('/api/usage/summary', 20000)
  const daemons = useApi<DaemonsPayload>('/api/daemons/status', 15000)
  const { events } = useLive()

  const orgList = orgs.data ?? []
  const counts = orchestra.data?.counts
  const sessionList = orchestra.data?.sessions ?? []
  const handoffList = orchestra.data?.handoffs ?? []

  const pendingReview =
    orgList.reduce((sum, o) => sum + (o.pending_proposals || 0), 0) +
    (counts?.pending_handoffs ?? 0)
  const tokens5h = usage.data?.usage?.session_5h?.total_tokens ?? 0
  const govLevel = usage.data?.governor?.level ?? 'ok'
  const rateLimited = Boolean(usage.data?.rate_limited ?? daemons.data?.rate_limited)

  if (orchestra.loading && orgs.loading) {
    return (
      <>
        <Header />
        <Loading label="天空を観測" />
      </>
    )
  }
  if (orchestra.error && orgs.error) {
    return (
      <>
        <Header />
        <ErrorNote message={orchestra.error} />
      </>
    )
  }

  return (
    <>
      <Header />

      {/* Firmament — the signature stage */}
      <Plate className="!p-0 overflow-hidden rise">
        <div className="relative">
          <div className="absolute left-5 top-5 z-10 flex items-center gap-3">
            <Tag tone="ice" live>
              Firmament · Live
            </Tag>
            <span className="mono text-[10px] tracking-[0.2em] text-faint uppercase">
              組織 × 稼働セッションの星座図
            </span>
          </div>
          <Firmament
            orgs={orgList}
            sessions={sessionList}
            handoffs={handoffList}
            theme={theme}
            height={460}
          />
          <div className="grid grid-cols-2 gap-px sm:grid-cols-4 border-t border-[color:var(--line)]">
            <Caption k="星 / 組織" v={String(orgList.length)} />
            <Caption k="稼働セッション" v={String(counts?.active_sessions ?? 0)} />
            <Caption k="エージェント" v={String(counts?.agents ?? 0)} />
            <Caption k="引き渡し" v={String(counts?.handoffs ?? 0)} />
          </div>
        </div>
      </Plate>

      {/* Headline figures */}
      <section className="mt-12 grid grid-cols-2 gap-y-10 gap-x-6 md:grid-cols-4">
        <Stat label="Organizations" value={orgList.length} tone="gold" sub="観測中の組織" />
        <Stat
          label="Live Agents"
          value={counts?.agents ?? 0}
          tone="ice"
          sub={`${counts?.active_sessions ?? 0} sessions active`}
        />
        <Stat
          label="Pending Review"
          value={pendingReview}
          tone="gold"
          sub="提案 + 引き渡し"
        />
        <Stat
          label="Tokens · 5h"
          value={compactNumber(tokens5h)}
          tone="plain"
          sub={`governor: ${govLevel}`}
        />
      </section>

      {/* Transmissions + Systems */}
      <section className="mt-14 grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Plate no="PL. 01" className="lg:col-span-7">
          <div className="mb-5 flex items-baseline justify-between">
            <h2 className="serif text-2xl">Transmissions</h2>
            <span className="kicker">live feed</span>
          </div>
          {events.length === 0 ? (
            <p className="text-dim text-sm py-8">
              まだ受信した更新はありません。デーモンが稼働すると、ここに動きが流れ込みます。
            </p>
          ) : (
            <ul className="flex flex-col">
              {events.slice(0, 9).map((ev, i) => (
                <li
                  key={ev.id ?? `${ev.type}-${i}`}
                  className="flex items-center gap-4 border-t border-[color:var(--line)] py-3 first:border-t-0"
                >
                  <span
                    className="dot shrink-0"
                    style={{
                      color:
                        ev.status === 'error'
                          ? 'var(--rose)'
                          : ev.status === 'pending'
                            ? 'var(--ice)'
                            : 'var(--green)',
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{ev.title || ev.operation || '更新'}</div>
                    <div className="truncate text-faint mono text-[11px] tracking-wide">
                      {ev.details || ev.org_name || ev.type || 'pantheon'}
                    </div>
                  </div>
                  <span className="mono text-faint text-[10px] tracking-wide shrink-0">
                    {relativeTime(ev.timestamp)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Plate>

        <Plate no="PL. 02" className="lg:col-span-5">
          <div className="mb-5 flex items-baseline justify-between">
            <h2 className="serif text-2xl">Systems</h2>
            {rateLimited ? (
              <Tag tone="rose">rate-limited</Tag>
            ) : (
              <Tag tone={GOVERNOR_TONE[govLevel] ?? 'green'}>{govLevel}</Tag>
            )}
          </div>
          <ul className="flex flex-col">
            {(daemons.data?.daemons ?? []).map((d) => {
              const running = Boolean(d.running)
              const ok = running && d.stale !== true
              return (
                <li
                  key={d.name}
                  className="flex items-center gap-3 border-t border-[color:var(--line)] py-3 first:border-t-0"
                >
                  <span
                    className="dot shrink-0"
                    style={{ color: ok ? 'var(--green)' : running ? 'var(--gold)' : 'var(--text-faint)' }}
                  />
                  <span className="flex-1 mono text-[12px] tracking-wide uppercase">{d.name}</span>
                  <span className="mono text-faint text-[10px] tracking-wider uppercase">
                    {!running ? '停止' : d.stale ? 'stale' : d.enabled === false ? 'paused' : '稼働'}
                  </span>
                </li>
              )
            })}
            {(daemons.data?.daemons ?? []).length === 0 ? (
              <li className="text-dim text-sm py-4">デーモン情報を取得できません。</li>
            ) : null}
          </ul>
          <a
            href="/pantheon"
            className="mt-5 inline-flex items-center gap-2 text-gold mono text-[11px] tracking-[0.16em] uppercase"
          >
            組織を巡る <ArrowIcon size={15} />
          </a>
        </Plate>
      </section>
    </>
  )
}

function Header() {
  return (
    <Exhibit
      index={1}
      kicker="The Observatory"
      title={
        <>
          天空を、
          <br />
          <em>ひと目で。</em>
        </>
      }
      lede="あなたの AI 組織群は、ひとつの星座です。健全度が輝度に、エージェント数が大きさに、稼働セッションが脈動に変わります。Pantheon の現在地を、観測するように見渡してください。"
    />
  )
}

function Caption({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-[color:var(--ink-1)] px-5 py-4">
      <div className="numeral text-3xl text-gold">{v}</div>
      <div className="kicker mt-1">{k}</div>
    </div>
  )
}
