import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Clock, FileText, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import * as Dialog from '@radix-ui/react-dialog'

import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import { statusBadge, statusLabel } from '@/lib/labels'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PageHeader } from '@/components/PageHeader'
import { AsyncBoundary } from '@/components/AsyncBoundary'
import { RefreshButton } from '@/components/RefreshButton'
import { EmptyState } from '@/components/EmptyState'
import { Tabs } from '@/components/Tabs'

type GoalHistoryItem = {
  id?: string
  goal: string
  org_name?: string
  result: string
  timestamp: string
  success?: boolean
}

type GoalHistoryApiItem = Partial<GoalHistoryItem> & {
  goal_text?: string
  summary?: string
  created_at?: string
  organization?: string
}

function normalizeGoalHistoryItem(item: GoalHistoryApiItem): GoalHistoryItem {
  return {
    id: item.id,
    goal: item.goal ?? item.goal_text ?? '—',
    org_name: item.org_name ?? item.organization,
    result: item.result ?? item.summary ?? '—',
    timestamp: item.timestamp ?? item.created_at ?? '',
    success: item.success,
  }
}

interface KnowledgeFile {
  path: string
  name: string
  size: number
  modified: number
  extension: string
}

interface KnowledgeFileDetail {
  path: string
  name: string
  content: string
  size: number
  modified: number
}

type DataTab = 'history' | 'knowledge'

const DATA_TABS: { value: DataTab; label: string }[] = [
  { value: 'history', label: 'ゴール履歴' },
  { value: 'knowledge', label: 'ナレッジ' },
]

function encodeFilePath(path: string) {
  return path.split('/').map(encodeURIComponent).join('/')
}

// ファイル名のクライアント側バリデーション（C034: 空/不正文字/パストラバーサル検査）
function validateFileName(name: string): string | null {
  if (!name.trim()) return 'ファイル名を入力してください。'
  if (name.includes('..') || name.includes('/') || name.includes('\\')) {
    return 'パスセパレータや ".." は使用できません。'
  }
  if (!/^[\w\-. ]+$/.test(name)) {
    return 'ファイル名に使用できない文字が含まれています。'
  }
  return null
}

type ConfirmState = {
  title: string
  description?: ReactNode
  confirmLabel: string
  run: () => Promise<void>
}

export function DataPage() {
  const [activeTab, setActiveTab] = useState<DataTab>('history')
  const [history, setHistory] = useState<GoalHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [knowledgeLoading, setKnowledgeLoading] = useState(false)
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null)
  const [knowledgeLoaded, setKnowledgeLoaded] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<KnowledgeFileDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [newFileContent, setNewFileContent] = useState('')
  const [fileNameError, setFileNameError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)

  const fileNameInputRef = useRef<HTMLInputElement>(null)

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      const items = await api<GoalHistoryApiItem[]>('GET', '/api/goals/history')
      setHistory(items.map(normalizeGoalHistoryItem))
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'データの読み込みに失敗しました。'
      setHistoryError(msg)
      toast.error(msg)
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const loadKnowledgeFiles = useCallback(async () => {
    setKnowledgeLoading(true)
    setKnowledgeError(null)
    try {
      const response = await api<{ files: KnowledgeFile[] }>('GET', '/api/knowledge/files')
      setFiles(response.files)
      setKnowledgeLoaded(true)
      if (selectedPath && !response.files.some((file) => file.path === selectedPath)) {
        setSelectedPath(null)
        setSelectedFile(null)
        setIsEditing(false)
        setEditContent('')
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'ナレッジ一覧の読み込みに失敗しました。'
      setKnowledgeError(msg)
      toast.error(msg)
    } finally {
      setKnowledgeLoading(false)
    }
  }, [selectedPath])

  const handleSelectFile = useCallback(async (path: string) => {
    setSelectedPath(path)
    setIsEditing(false)
    setDetailLoading(true)
    setDetailError(null)
    try {
      const file = await api<KnowledgeFileDetail>('GET', `/api/knowledge/files/${encodeFilePath(path)}`)
      setSelectedFile(file)
      setEditContent(file.content)
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'ファイルの読み込みに失敗しました。'
      setDetailError(msg)
      toast.error(msg)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const refreshKnowledge = useCallback(async () => {
    await loadKnowledgeFiles()
    if (selectedPath) {
      await handleSelectFile(selectedPath)
    }
  }, [handleSelectFile, loadKnowledgeFiles, selectedPath])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  useEffect(() => {
    if (activeTab === 'knowledge' && !knowledgeLoaded) {
      void loadKnowledgeFiles()
    }
  }, [activeTab, knowledgeLoaded, loadKnowledgeFiles])

  // ConfirmDialog 経由の破壊操作用。失敗時は再 throw してダイアログを開いたままにする。
  const directRun = async (fn: () => Promise<unknown>, successMsg: string): Promise<void> => {
    try {
      await fn()
      toast.success(successMsg)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作に失敗しました。')
      throw err
    }
  }

  const handleClearHistoryClick = () => {
    setConfirm({
      title: '履歴をすべて削除しますか？',
      description: (
        <>
          {history.length} 件のゴール実行履歴をすべて削除します。
          <strong>この操作は取り消せません。</strong>
        </>
      ),
      confirmLabel: `${history.length} 件を削除`,
      run: async () => {
        await directRun(async () => {
          await api('DELETE', '/api/goals/history')
          setHistory([])
        }, '履歴を削除しました。')
      },
    })
  }

  const handleDeleteFileClick = () => {
    if (!selectedFile) return
    setConfirm({
      title: 'ファイルを削除しますか？',
      description: (
        <>
          「{selectedFile.name}」を削除します。<strong>この操作は取り消せません。</strong>
        </>
      ),
      confirmLabel: '削除',
      run: async () => {
        await directRun(async () => {
          if (!selectedFile) return
          setDeleting(true)
          try {
            await api('DELETE', `/api/knowledge/files/${encodeFilePath(selectedFile.path)}`)
          } finally {
            setDeleting(false)
          }
          setSelectedPath(null)
          setSelectedFile(null)
          setIsEditing(false)
          setEditContent('')
          await loadKnowledgeFiles()
        }, 'ファイルを削除しました。')
      },
    })
  }

  const handleSave = async () => {
    if (!selectedFile) return
    setSaving(true)
    try {
      await api('PUT', `/api/knowledge/files/${encodeFilePath(selectedFile.path)}`, {
        content: editContent,
      })
      toast.success('ファイルを保存しました。')
      setSelectedFile({
        ...selectedFile,
        content: editContent,
        modified: Date.now() / 1000,
        size: new TextEncoder().encode(editContent).length,
      })
      setIsEditing(false)
      await loadKnowledgeFiles()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存に失敗しました。')
    } finally {
      setSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    if (selectedFile) setEditContent(selectedFile.content)
  }

  const closeCreateModal = () => {
    setShowCreateModal(false)
    setNewFileName('')
    setNewFileContent('')
    setFileNameError(null)
  }

  const handleCreate = async () => {
    const name = newFileName.trim()
    const validationError = validateFileName(name)
    if (validationError) {
      setFileNameError(validationError)
      fileNameInputRef.current?.focus()
      return
    }
    setFileNameError(null)

    setCreating(true)
    try {
      const result = await api<{ status: string; path: string }>('POST', '/api/knowledge/files', {
        name,
        content: newFileContent,
      })
      toast.success('ファイルを作成しました。')
      closeCreateModal()
      await loadKnowledgeFiles()
      await handleSelectFile(result.path)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ファイル作成に失敗しました。')
    } finally {
      setCreating(false)
    }
  }

  const handleRefresh = () => {
    if (activeTab === 'history') {
      void loadHistory()
    } else {
      void refreshKnowledge()
    }
  }

  const isRefreshBusy = historyLoading || knowledgeLoading || detailLoading

  return (
    <>
      <PageHeader
        title="データ管理"
        subtitle="ゴール履歴と knowledge 配下の Markdown ファイルを管理できます。"
        actions={<RefreshButton onClick={handleRefresh} busy={isRefreshBusy} />}
      />

      <div className="page-content flex flex-col gap-4">
        <Tabs
          tabs={DATA_TABS}
          value={activeTab}
          onChange={setActiveTab}
          ariaLabel="データ管理タブ"
        />

        {activeTab === 'history' ? (
          <div className="flex flex-col gap-3">
            <AsyncBoundary
              loading={historyLoading}
              error={historyError}
              onRetry={loadHistory}
              loadingText="データを読み込み中…"
              isEmpty={history.length === 0}
              emptyIcon={Clock}
              emptyTitle="実行履歴がありません"
              emptyHint="ゴールページからゴールを実行すると、ここに履歴が記録されます。"
            >
              <>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-muted text-sm">{history.length} 件の実行記録</div>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={handleClearHistoryClick}
                  >
                    <Trash2 size={13} />
                    履歴をクリア
                  </button>
                </div>

                <div className="data-table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>ゴール</th>
                        <th>組織</th>
                        <th>成否</th>
                        <th>結果</th>
                        <th>実行日時</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((item, i) => (
                        <tr key={item.id ?? i}>
                          <td className="data-goal-cell">{item.goal}</td>
                          <td>
                            {item.org_name ? (
                              <span className="badge badge-neutral">{item.org_name}</span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                          <td>
                            {item.success !== undefined ? (
                              <span
                                className={`badge ${statusBadge(item.success ? 'success' : 'failed')}`}
                              >
                                {statusLabel(item.success ? 'success' : 'failed')}
                              </span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                          <td className="data-result-cell">{item.result}</td>
                          <td className="text-muted whitespace-nowrap">
                            {item.timestamp ? formatDateTime(item.timestamp) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            </AsyncBoundary>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-muted text-sm">{files.length} 件のナレッジファイル</div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setShowCreateModal(true)}
              >
                <Plus size={13} />
                新規作成
              </button>
            </div>

            <AsyncBoundary
              loading={knowledgeLoading && !knowledgeLoaded}
              error={knowledgeError}
              onRetry={loadKnowledgeFiles}
              loadingText="ナレッジを読み込み中…"
            >
              <div className="card">
                <div className="card-body knowledge-layout">
                  <div className="knowledge-file-list" aria-label="ナレッジファイル一覧">
                    {files.length === 0 ? (
                      <div className="knowledge-list-empty">
                        <EmptyState
                          icon={FileText}
                          title="ナレッジファイルがありません"
                          hint="右上の「新規作成」から追加できます。"
                          action={
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => setShowCreateModal(true)}
                            >
                              <Plus size={13} />
                              新規作成
                            </button>
                          }
                        />
                      </div>
                    ) : (
                      files.map((file) => (
                        <button
                          key={file.path}
                          type="button"
                          className={`knowledge-file-item ${selectedPath === file.path ? 'active' : ''}`}
                          onClick={() => void handleSelectFile(file.path)}
                          aria-current={selectedPath === file.path ? true : undefined}
                        >
                          <div className="knowledge-file-icon">
                            <FileText size={16} />
                          </div>
                          <div className="knowledge-file-info">
                            <div className="knowledge-file-name">{file.name}</div>
                            <div className="knowledge-file-meta">
                              {file.size < 1024
                                ? `${file.size} B`
                                : file.size < 1024 * 1024
                                  ? `${(file.size / 1024).toFixed(1)} KB`
                                  : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}{' '}
                              · {formatDateTime(file.modified)}
                            </div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>

                  <div className="knowledge-detail-panel">
                    <AsyncBoundary
                      loading={detailLoading}
                      error={detailError}
                      onRetry={selectedPath ? () => void handleSelectFile(selectedPath) : undefined}
                      loadingText="ファイルを読み込み中…"
                    >
                      {selectedFile ? (
                        <>
                          <div className="knowledge-detail-header">
                            <div className="knowledge-detail-title-wrap">
                              <h3>{selectedFile.name}</h3>
                              <div className="knowledge-file-meta">
                                {selectedFile.path} ·{' '}
                                {selectedFile.size < 1024
                                  ? `${selectedFile.size} B`
                                  : selectedFile.size < 1024 * 1024
                                    ? `${(selectedFile.size / 1024).toFixed(1)} KB`
                                    : `${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB`}{' '}
                                · {formatDateTime(selectedFile.modified)}
                              </div>
                            </div>
                            <div className="knowledge-detail-actions">
                              {!isEditing ? (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => setIsEditing(true)}
                                  >
                                    編集
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-danger"
                                    onClick={handleDeleteFileClick}
                                    disabled={deleting}
                                  >
                                    削除
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-primary"
                                    onClick={() => void handleSave()}
                                    disabled={saving || editContent === selectedFile.content}
                                  >
                                    {saving ? '保存中…' : '保存'}
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={handleCancelEdit}
                                  >
                                    キャンセル
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                          {isEditing ? (
                            <textarea
                              className="knowledge-editor"
                              value={editContent}
                              onChange={(event) => setEditContent(event.target.value)}
                              aria-label="ファイル内容"
                            />
                          ) : (
                            <pre className="knowledge-preview">
                              {selectedFile.content || '内容がありません。'}
                            </pre>
                          )}
                        </>
                      ) : (
                        <div className="knowledge-empty-state">
                          <EmptyState
                            icon={FileText}
                            title="ファイルを選択してください"
                            hint="左側の一覧からナレッジファイルを選ぶと内容を確認できます。"
                          />
                        </div>
                      )}
                    </AsyncBoundary>
                  </div>
                </div>
              </div>
            </AsyncBoundary>
          </div>
        )}
      </div>

      {/* ナレッジ新規作成ダイアログ（Radix Dialog — C025: フォーカストラップ/Escape/ARIA 準拠） */}
      <Dialog.Root
        open={showCreateModal}
        onOpenChange={(next) => {
          if (!creating) {
            if (!next) closeCreateModal()
            else setShowCreateModal(true)
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className="dialog knowledge-create-dialog"
            onOpenAutoFocus={(event) => {
              event.preventDefault()
              fileNameInputRef.current?.focus()
            }}
          >
            <Dialog.Title className="dialog-title">ナレッジファイルの新規作成</Dialog.Title>
            <Dialog.Description className="dialog-desc">
              knowledge ディレクトリに Markdown ファイルを追加します。
            </Dialog.Description>

            <form
              onSubmit={(event) => {
                event.preventDefault()
                void handleCreate()
              }}
            >
              <div className="input-group">
                <label className="input-label" htmlFor="knowledge-file-name">
                  ファイル名
                </label>
                <input
                  id="knowledge-file-name"
                  ref={fileNameInputRef}
                  type="text"
                  className="input"
                  placeholder="例: my_knowledge.md"
                  value={newFileName}
                  onChange={(event) => {
                    setNewFileName(event.target.value)
                    if (fileNameError) setFileNameError(null)
                  }}
                  aria-describedby={fileNameError ? 'knowledge-file-name-error' : undefined}
                  aria-invalid={fileNameError ? true : undefined}
                  required
                />
                {fileNameError ? (
                  <p id="knowledge-file-name-error" className="text-sm text-red-500 mt-1">
                    {fileNameError}
                  </p>
                ) : null}
              </div>
              <div className="input-group knowledge-create-body">
                <label className="input-label" htmlFor="knowledge-file-content">
                  内容
                </label>
                <textarea
                  id="knowledge-file-content"
                  className="knowledge-editor"
                  placeholder="内容を入力..."
                  value={newFileContent}
                  onChange={(event) => setNewFileContent(event.target.value)}
                  aria-label="ファイル内容"
                />
              </div>
              <div className="dialog-actions">
                <Dialog.Close asChild>
                  <button type="button" className="btn btn-secondary" disabled={creating}>
                    キャンセル
                  </button>
                </Dialog.Close>
                <button type="submit" className="btn btn-primary" disabled={creating}>
                  {creating ? '作成中…' : '作成'}
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* 破壊操作確認ダイアログ（ConfirmDialog — C002） */}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) setConfirm(null)
        }}
        title={confirm?.title ?? ''}
        description={confirm?.description}
        confirmLabel={confirm?.confirmLabel ?? '実行'}
        onConfirm={confirm?.run ?? (() => Promise.resolve())}
      />
    </>
  )
}
