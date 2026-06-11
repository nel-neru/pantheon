import { useCallback, useEffect, useState } from 'react'

export type Theme = 'nocturne' | 'daylight'
const KEY = 'atelier-theme'

function initialTheme(): Theme {
  if (typeof window === 'undefined') return 'nocturne'
  const stored = window.localStorage.getItem(KEY)
  return stored === 'daylight' ? 'daylight' : 'nocturne'
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem(KEY, theme)
    } catch {
      // private mode etc. — ignore
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((t) => (t === 'nocturne' ? 'daylight' : 'nocturne'))
  }, [])

  return [theme, toggle]
}
