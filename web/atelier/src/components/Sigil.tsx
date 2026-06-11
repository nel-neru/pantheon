// 名前から決定論的に描く星座グリフ（組織ごとの固有マーク）。RNG 不使用＝再描画で不変。
function rngFrom(seed: string): () => number {
  let s = 2166136261
  for (let i = 0; i < seed.length; i++) {
    s ^= seed.charCodeAt(i)
    s = Math.imul(s, 16777619)
  }
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0
    return s / 4294967296
  }
}

export function Sigil({
  seed,
  size = 60,
  color = 'currentColor',
}: {
  seed: string
  size?: number
  color?: string
}) {
  const rnd = rngFrom(seed || 'pantheon')
  const n = 5 + Math.floor(rnd() * 4)
  const pts = Array.from({ length: n }, () => ({
    x: 9 + rnd() * 42,
    y: 9 + rnd() * 42,
    r: 0.9 + rnd() * 1.8,
  }))
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  return (
    <svg width={size} height={size} viewBox="0 0 60 60" fill="none" aria-hidden="true">
      <path d={path} stroke={color} strokeWidth={0.8} strokeOpacity={0.45} strokeLinejoin="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={p.r} fill={color} fillOpacity={0.85} />
      ))}
    </svg>
  )
}
