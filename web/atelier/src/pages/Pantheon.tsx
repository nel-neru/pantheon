import { useState } from 'react'

import { Sigil } from '@/components/Sigil'
import { Exhibit, EmptyState, ErrorNote, Loading, Plate, Tag } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { clamp, pad2, relativeTime } from '@/lib/format'
import type { OrgSummary } from '@/lib/types'

type Filter = 'all' | 'live' | 'system'

const STATUS_TONE: Record<string, 'green' | 'gold' | 'ice' | 'rose' | 'neutral'> = {
  active: 'green',
  paused: 'gold',
  archived: 'neutral',
  error: 'rose',
}

export function Pantheon() {
  const { data, loading, error } = useApi<OrgSummary[]>('/api/organizations', 30000)
  const [filter, setFilter] = useState<Filter>('all')

  const all = data ?? []
  const orgs = all.filter((o) => {
    if (filter === 'live') return (o.pending_proposals || 0) > 0 || o.status === 'active'
    if (filter === 'system') return o.is_system
    return true
  })

  return (
    <>
      <Exhibit
        index={2}
        kicker="The Pantheon"
        title={
          <>
            神々の、<em>万神殿。</em>
          </>
        }
        lede="一つひとつの組織が、固有の星座を持ちます。健全度・自律度・改善速度を一枚のプレートに刻んだ、生きたカタログ。"
        actions={
          <div className="flex items-center gap-2">
            {(['all', 'live', 'system'] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                className="btn"
                style={
                  filter === f
                    ? { borderColor: 'var(--gold)', color: 'var(--gold)' }
                    : undefined
                }
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        }
      />

      {loading && !data ? <Loading label="カタログを展開" /> : null}
      {error && !data ? <ErrorNote message={error} /> : null}
      {data && orgs.length === 0 ? (
        <EmptyState title="まだ組織がありません" hint="pantheon org create で最初の星を据えましょう" />
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {orgs.map((org, i) => (
          <OrgPlate key={org.id} org={org} index={i + 1} />
        ))}
      </div>
    </>
  )
}

function OrgPlate({ org, index }: { org: OrgSummary; index: number }) {
  const health = clamp(org.health_score || 0, 0, 100)
  const autonomy = clamp(org.autonomy_score || 0, 0, 100)
  return (
    <Plate no={`ORG · ${pad2(index)}`} className="flex flex-col rise">
      <div className="flex items-start justify-between">
        <div className="text-gold">
          <Sigil seed={org.name} size={56} />
        </div>
        <Tag tone={STATUS_TONE[org.status] ?? 'neutral'}>{org.status}</Tag>
      </div>

      <h3 className="serif mt-4 text-[26px] leading-tight">{org.name}</h3>
      <p className="text-dim mt-2 line-clamp-2 text-sm min-h-[2.6em]">
        {org.purpose || '目的は未設定です。'}
      </p>

      <div className="mt-5 flex flex-col gap-3">
        <Meter label="健全度" value={health} tone="var(--green)" />
        <Meter label="自律度" value={autonomy} tone="var(--ice)" />
      </div>

      <hr className="hairline my-5" />
      <div className="flex items-center justify-between mono text-[11px] tracking-wide text-faint">
        <span>
          <span className="text-gold">{org.total_agents}</span> agents
        </span>
        <span>
          <span style={{ color: org.pending_proposals ? 'var(--gold)' : undefined }}>
            {org.pending_proposals}
          </span>{' '}
          pending
        </span>
        <span>{relativeTime(org.last_active)}</span>
      </div>

      {org.is_system ? (
        <div className="mt-3">
          <Tag tone="gold">system</Tag>
        </div>
      ) : null}
    </Plate>
  )
}

function Meter({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="kicker">{label}</span>
        <span className="numeral text-lg" style={{ color: tone }}>
          {Math.round(value)}
        </span>
      </div>
      <div className="mt-1.5 h-px w-full" style={{ background: 'var(--line)' }}>
        <div className="h-px" style={{ width: `${value}%`, background: tone }} />
      </div>
    </div>
  )
}
