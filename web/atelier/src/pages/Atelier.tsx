import { Sigil } from '@/components/Sigil'
import { Exhibit, EmptyState, ErrorNote, Loading, Plate } from '@/components/ui'
import { useApi } from '@/hooks/useApi'
import { pad2 } from '@/lib/format'
import type { DesignStyle, Palette, Persona } from '@/lib/types'

function paletteEntries(palette: Palette): Array<[string, string]> {
  const order: Array<keyof Palette> = ['primary', 'secondary', 'accent', 'background']
  return order
    .map((k) => [k, palette[k]] as [string, string | undefined])
    .filter((pair): pair is [string, string] => Boolean(pair[1]))
}

export function Atelier() {
  const styles = useApi<DesignStyle[]>('/api/design-styles')
  const personas = useApi<Persona[]>('/api/personas')

  return (
    <>
      <Exhibit
        index={3}
        kicker="The Atelier"
        title={
          <>
            纏う、<em>色と声。</em>
          </>
        }
        lede="どんな美意識にも、どんな語り口にも染まれること。デザインスタイルとペルソナは、組織が世界に現れるときの衣装です。ここはその標本室。"
      />

      <SectionLabel n={1} title="Design Styles" note="palette specimens" />
      {styles.loading && !styles.data ? <Loading label="色見本を展開" /> : null}
      {styles.error && !styles.data ? <ErrorNote message={styles.error} /> : null}
      {styles.data && styles.data.length === 0 ? (
        <EmptyState title="デザインスタイルがありません" />
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {(styles.data ?? []).map((style, i) => (
          <StyleSpecimen key={style.id} style={style} index={i + 1} />
        ))}
      </div>

      <div className="mt-20" />
      <SectionLabel n={2} title="Personas" note="voices" />
      {personas.loading && !personas.data ? <Loading label="声を集める" /> : null}
      {personas.data && personas.data.length === 0 ? (
        <EmptyState title="ペルソナがありません" hint="config/personas に追加できます" />
      ) : null}

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {(personas.data ?? []).map((p, i) => (
          <Plate key={p.id} no={`P · ${pad2(i + 1)}`} className="flex items-center gap-4 rise">
            <div className="text-ice shrink-0">
              <Sigil seed={`persona:${p.id}`} size={48} />
            </div>
            <div className="min-w-0">
              <div className="serif text-xl leading-tight truncate">{p.name}</div>
              <div className="text-dim text-sm truncate">{p.role || '—'}</div>
              <div className="mono text-faint text-[10px] tracking-wider mt-1">{p.id}</div>
            </div>
          </Plate>
        ))}
      </div>
    </>
  )
}

function StyleSpecimen({ style, index }: { style: DesignStyle; index: number }) {
  const entries = paletteEntries(style.palette || {})
  return (
    <Plate no={`STY · ${pad2(index)}`} className="!p-0 overflow-hidden flex flex-col rise">
      <div className="flex h-32 w-full">
        {entries.length === 0 ? (
          <div className="flex-1" style={{ background: 'var(--ink-2)' }} />
        ) : (
          entries.map(([k, color]) => (
            <div
              key={k}
              className="group relative flex-1 transition-[flex] duration-500"
              style={{ background: color }}
              title={`${k} ${color}`}
            >
              <span
                className="absolute bottom-2 left-2 mono text-[9px] tracking-wider opacity-0 transition-opacity group-hover:opacity-100"
                style={{ color: 'rgba(255,255,255,0.9)', mixBlendMode: 'difference' }}
              >
                {color}
              </span>
            </div>
          ))
        )}
      </div>
      <div className="p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="serif text-2xl">{style.name}</h3>
          <span className="mono text-faint text-[10px] tracking-wider uppercase">{style.id}</span>
        </div>
        <p className="text-dim mt-2 text-sm line-clamp-3 min-h-[3.8em]">{style.description}</p>
        {style.font_family ? (
          <div className="mt-4 border-t border-[color:var(--line)] pt-3">
            <span className="kicker">typeface</span>
            <div className="text-sm mt-1 truncate" style={{ fontFamily: style.font_family }}>
              {style.font_family}
            </div>
          </div>
        ) : null}
      </div>
    </Plate>
  )
}

function SectionLabel({ n, title, note }: { n: number; title: string; note: string }) {
  return (
    <div className="mb-6 flex items-center gap-4">
      <span className="mono text-gold text-xs tracking-[0.2em]">{pad2(n)}</span>
      <h2 className="serif text-3xl">{title}</h2>
      <span className="kicker">{note}</span>
      <span className="ml-2 h-px flex-1" style={{ background: 'var(--line)' }} />
    </div>
  )
}
