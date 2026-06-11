import { createContext, useContext, type ReactNode } from 'react'

import { useLiveFeed, type LiveEvent } from './useLiveFeed'

type LiveValue = { connected: boolean; events: LiveEvent[] }

const LiveContext = createContext<LiveValue>({ connected: false, events: [] })

// アプリ全体で 1 本だけ /ws/updates を張り、配下の画面が共有する。
export function LiveProvider({ children }: { children: ReactNode }) {
  const value = useLiveFeed(40)
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}

export function useLive(): LiveValue {
  return useContext(LiveContext)
}
