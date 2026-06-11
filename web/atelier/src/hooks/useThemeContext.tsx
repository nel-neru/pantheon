import { createContext, useContext, type ReactNode } from 'react'

import { useTheme, type Theme } from './useTheme'

type ThemeValue = { theme: Theme; toggle: () => void }

const ThemeContext = createContext<ThemeValue>({ theme: 'nocturne', toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, toggle] = useTheme()
  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}

export function useThemeCtx(): ThemeValue {
  return useContext(ThemeContext)
}
