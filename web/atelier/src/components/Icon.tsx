import type { SVGProps } from 'react'

// 自前の線画アイコン群（依存ゼロ・currentColor 追従）。アート GUI のトーンに合わせ、
// 細い 1.4 ストロークで統一する。
type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function base({ size = 20, ...rest }: IconProps): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.4,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    ...rest,
  }
}

export function ObservatoryIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="2.4" />
      <ellipse cx="12" cy="12" rx="9.2" ry="3.6" />
      <ellipse cx="12" cy="12" rx="9.2" ry="3.6" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="9.2" ry="3.6" transform="rotate(120 12 12)" />
    </svg>
  )
}

export function PantheonIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 9 12 3l9 6" />
      <path d="M4.5 9v8M9 9v8M15 9v8M19.5 9v8" />
      <path d="M3 20h18" />
    </svg>
  )
}

export function AtelierIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.9 1.8-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-.9.8-1.6 1.7-1.6H16a5 5 0 0 0 5-5c0-3.9-4-7-9-7Z" />
      <circle cx="7.5" cy="11" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="16.5" cy="11" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function SignalsIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 12c2.5 0 2.5-6 5-6s2.5 12 5 12 2.5-6 5-6" />
      <circle cx="3" cy="12" r="0.7" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function InboxIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 13l2.5-7.5A2 2 0 0 1 7.4 4h9.2a2 2 0 0 1 1.9 1.5L21 13" />
      <path d="M3 13h5l1.2 2.2a1 1 0 0 0 .9.55h3.8a1 1 0 0 0 .9-.55L16 13h5v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    </svg>
  )
}

export function SunIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2.5M12 19.5V22M22 12h-2.5M4.5 12H2M19 5l-1.8 1.8M6.8 17.2 5 19M19 19l-1.8-1.8M6.8 6.8 5 5" />
    </svg>
  )
}

export function MoonIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.3 6.3 0 0 0 10.5 10.5Z" />
    </svg>
  )
}

export function ArrowIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

export function HandbookIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 0 4 20.5Z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5A1.5 1.5 0 0 1 20 20.5Z" />
      <path d="M12 5.5V19" />
    </svg>
  )
}

export function PantheonMark(p: IconProps) {
  // ブランドマーク：万神殿のペディメント＋柱（星座にも見える幾何）
  return (
    <svg {...base({ size: 28, ...p })} strokeWidth={1.3}>
      <path d="M4 9 12 3.5 20 9" />
      <path d="M5.5 9v8.5M10 9v8.5M14 9v8.5M18.5 9v8.5" />
      <path d="M4 18.5h16" />
      <circle cx="12" cy="6.4" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  )
}
