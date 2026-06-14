import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState } from 'react'

import { getApiToken, setApiToken } from '@/lib/token'

/**
 * 401 集中ハンドリング用のトークン復帰ダイアログ（C010）。
 *
 * サーバが PANTHEON_API_TOKEN を要求していて未認証/期限切れのとき、api.ts が
 * `pantheon:unauthorized` イベントを発火する。本ダイアログはそれを購読して開き、
 * トークンの貼り付け→保存(setApiToken)→再読み込みで回復させる。これまで各ページが
 * 赤エラーを出すだけで復帰手段が無かった問題を解消する。
 */
export function AuthTokenDialog() {
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState('')

  useEffect(() => {
    const handler = () => {
      setToken(getApiToken())
      setOpen(true)
    }
    window.addEventListener('pantheon:unauthorized', handler)
    return () => window.removeEventListener('pantheon:unauthorized', handler)
  }, [])

  const save = () => {
    const trimmed = token.trim()
    if (!trimmed) return
    setApiToken(trimmed)
    if (typeof window !== 'undefined') window.location.reload()
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog confirm-dialog">
          <Dialog.Title className="dialog-title">APIトークンが必要です</Dialog.Title>
          <Dialog.Description className="dialog-desc">
            このサーバは認証トークン（PANTHEON_API_TOKEN）を要求しています。発行されたトークンを貼り付けて保存してください。
          </Dialog.Description>
          <div className="confirm-word">
            <label className="confirm-word-label" htmlFor="api-token-input">
              APIトークン
            </label>
            <input
              id="api-token-input"
              className="input"
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') save()
              }}
              autoComplete="off"
              aria-label="APIトークン"
            />
          </div>
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="btn btn-secondary">
                後で
              </button>
            </Dialog.Close>
            <button type="button" className="btn btn-primary" onClick={save} disabled={!token.trim()}>
              保存して再読み込み
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
