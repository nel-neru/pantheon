import { Navigate, Route, Routes } from 'react-router-dom'

import { Shell } from '@/components/Shell'
import { Observatory } from '@/pages/Observatory'
import { Pantheon } from '@/pages/Pantheon'
import { Atelier } from '@/pages/Atelier'
import { Signals } from '@/pages/Signals'
import { Inbox } from '@/pages/Inbox'
import { Handbook } from '@/pages/Handbook'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Observatory />} />
        <Route path="/pantheon" element={<Pantheon />} />
        <Route path="/atelier" element={<Atelier />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/handbook" element={<Handbook />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
