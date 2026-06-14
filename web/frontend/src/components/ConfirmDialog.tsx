import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** true で確認ボタンを danger 配色に（既定）。false で primary。 */
  destructive?: boolean
  /** 設定すると「名前一致確認」モード — この文字列を入力するまで確認不可。 */
  confirmWord?: string
  confirmWordLabel?: ReactNode
  /** 確認時の処理。Promise を返すと完了まで自動で実行中（ボタン無効）になる。失敗時は開いたまま。 */
  onConfirm: () => void | Promise<void>
}

/**
 * 破壊的/不可逆/外部送信の操作に必須化する統一確認ダイアログ。
 *
 * Radix Dialog ベースなので Escape・フォーカストラップ・初期フォーカス・aria-modal を
 * 標準で備える。`confirmWord` を渡すと「名前一致確認」モード（重大操作向け）になる。
 * 既存の `.dialog*` スタイルを再利用する（見た目の一貫性）。
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = '実行',
  cancelLabel = 'キャンセル',
  destructive = true,
  confirmWord,
  confirmWordLabel,
  onConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('')
  const [pending, setPending] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) setTyped('')
  }, [open])

  const needsWord = Boolean(confirmWord)
  const wordOk = !needsWord || typed.trim() === (confirmWord ?? '').trim()

  const handleConfirm = async () => {
    if (!wordOk || pending) return
    try {
      setPending(true)
      await onConfirm()
      onOpenChange(false)
    } catch {
      // 失敗時は閉じない（呼び出し側が toast 等でエラーを通知する想定）。再試行できる。
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!pending) onOpenChange(next)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog confirm-dialog"
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            if (needsWord) inputRef.current?.focus()
            else cancelRef.current?.focus()
          }}
        >
          <Dialog.Title className="dialog-title">{title}</Dialog.Title>
          {description ? (
            <Dialog.Description className="dialog-desc">{description}</Dialog.Description>
          ) : (
            // a11y: Radix は Description を推奨する。無い場合も警告を避けるため空で宣言。
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}

          {needsWord ? (
            <div className="confirm-word">
              <label className="confirm-word-label" htmlFor="confirm-word-input">
                {confirmWordLabel ?? (
                  <>
                    確認のため <code>{confirmWord}</code> と入力してください
                  </>
                )}
              </label>
              <input
                id="confirm-word-input"
                ref={inputRef}
                className="input"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void handleConfirm()
                }}
                aria-label="確認文字列"
                autoComplete="off"
              />
            </div>
          ) : null}

          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button ref={cancelRef} type="button" className="btn btn-secondary" disabled={pending}>
                {cancelLabel}
              </button>
            </Dialog.Close>
            <button
              type="button"
              className={cn('btn', destructive ? 'btn-danger' : 'btn-primary')}
              onClick={() => void handleConfirm()}
              disabled={!wordOk || pending}
            >
              {pending ? '処理中…' : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
