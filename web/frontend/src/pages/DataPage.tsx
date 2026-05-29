import { useCallback, useEffect, useState } from 'react'
import { Clock, FileText, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { formatDate } from '@/lib/utils'

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

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function encodeFilePath(path: string) {
  return path.split('/').map(encodeURIComponent).join('/')
}

export function DataPage() {
  const [activeTab, setActiveTab] = useState<DataTab>('history')
  const [history, setHistory] = useState<GoalHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [clearing, setClearing] = useState(false)

  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [knowledgeLoading, setKnowledgeLoading] = useState(false)
  const [knowledgeLoaded, setKnowledgeLoaded] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<KnowledgeFileDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [newFileContent, setNewFileContent] = useState('')
  const [creating, setCreating] = useState(false)

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const items = await api<GoalHistoryApiItem[]>('GET', '/api/goals/history')
      setHistory(items.map(normalizeGoalHistoryItem))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'データの読み込みに失敗しました。')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const loadKnowledgeFiles = useCallback(async () => {
    setKnowledgeLoading(true)
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
      toast.error(error instanceof Error ? error.message : 'ナレッジ一覧の読み込みに失敗しました。')
    } finally {
      setKnowledgeLoading(false)
    }
  }, [selectedPath])

  const handleSelectFile = useCallback(async (path: string) => {
    setSelectedPath(path)
    setIsEditing(false)
    setDetailLoading(true)
    try {
      const file = await api<KnowledgeFileDetail>('GET', `/api/knowledge/files/${encodeFilePath(path)}`)
      setSelectedFile(file)
      setEditContent(file.content)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ファイルの読み込みに失敗しました。')
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

  const clearHistory = async () => {
    if (!window.confirm('ゴール実行履歴をすべて削除しますか？')) return
    setClearing(true)
    try {
      await api('DELETE', '/api/goals/history')
      toast.success('履歴を削除しました。')
      setHistory([])
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '削除に失敗しました。')
    } finally {
      setClearing(false)
    }
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

  const handleDelete = async () => {
    if (!selectedFile) return
    if (!window.confirm(`${selectedFile.name} を削除しますか？`)) return

    setDeleting(true)
    try {
      await api('DELETE', `/api/knowledge/files/${encodeFilePath(selectedFile.path)}`)
      toast.success('ファイルを削除しました。')
      setSelectedPath(null)
      setSelectedFile(null)
      setIsEditing(false)
      setEditContent('')
      await loadKnowledgeFiles()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '削除に失敗しました。')
    } finally {
      setDeleting(false)
    }
  }

  const handleCreate = async () => {
    const name = newFileName.trim()
    if (!name) {
      toast.error('ファイル名を入力してください。')
      return
    }

    setCreating(true)
    try {
      const result = await api<{ status: string; path: string }>('POST', '/api/knowledge/files', {
        name,
        content: newFileContent,
      })
      toast.success('ファイルを作成しました。')
      setShowCreateModal(false)
      setNewFileName('')
      setNewFileContent('')
      await loadKnowledgeFiles()
      await handleSelectFile(result.path)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'ファイル作成に失敗しました。')
    } finally {
      setCreating(false)
    }
  }

  const handleRefresh = async () => {
    if (activeTab === 'history') {
      await loadHistory()
      return
    }
    await refreshKnowledge()
  }

  return (
    <>
      <header className="page-header">
        <div>
          <div className="page-title">データ管理</div>
          <p className="page-subtitle">ゴール履歴と knowledge 配下の Markdown ファイルを管理できます。</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void handleRefresh()}
            disabled={historyLoading || knowledgeLoading || detailLoading}
          >
            <RefreshCw size={13} className={historyLoading || knowledgeLoading ? 'spin' : ''} />
            再読み込み
          </button>
        </div>
      </header>

      <div className="page-content flex flex-col gap-4">
        <div className="data-tabs">
          <button
            type="button"
            className={`data-tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            ゴール履歴
          </button>
          <button
            type="button"
            className={`data-tab ${activeTab === 'knowledge' ? 'active' : ''}`}
            onClick={() => setActiveTab('knowledge')}
          >
            ナレッジ
          </button>
        </div>

        {activeTab === 'history' ? (
          <div className="flex flex-col gap-3">
            {historyLoading ? (
              <div className="card">
                <div className="card-body flex items-center gap-3">
                  <div className="spinner" />
                  <div className="text-muted">データを読み込み中…</div>
                </div>
              </div>
            ) : null}

            {!historyLoading ? (
              <>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-muted text-sm">{history.length} 件の実行記録</div>
                  {history.length > 0 ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ color: 'var(--color-danger)' }}
                      onClick={clearHistory}
                      disabled={clearing}
                    >
                      <Trash2 size={13} />
                      履歴をクリア
                    </button>
                  ) : null}
                </div>

                {history.length === 0 ? (
                  <div className="card">
                    <div className="card-body">
                      <div className="empty-state">
                        <Clock className="empty-state-icon" size={28} />
                        <h3>実行履歴がありません</h3>
                        <p>ゴールページからゴールを実行すると、ここに履歴が記録されます。</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="data-table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>ゴール</th>
                          <th>組織</th>
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
                            <td className="data-result-cell">{item.result}</td>
                            <td className="text-muted whitespace-nowrap">
                              {item.timestamp ? formatDate(item.timestamp) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-muted text-sm">{files.length} 件のナレッジファイル</div>
              <div className="flex items-center gap-2">
                <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
                  <Plus size={13} />
                  新規作成
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void refreshKnowledge()}
                  disabled={knowledgeLoading || detailLoading}
                >
                  <RefreshCw size={13} className={knowledgeLoading ? 'spin' : ''} />
                  更新
                </button>
              </div>
            </div>

            <div className="card">
              <div className="card-body knowledge-layout">
                <div className="knowledge-file-list" aria-label="ナレッジファイル一覧">
                  {knowledgeLoading && files.length === 0 ? (
                    <div className="knowledge-list-empty text-muted">ナレッジを読み込み中…</div>
                  ) : null}

                  {!knowledgeLoading && files.length === 0 ? (
                    <div className="knowledge-list-empty text-muted">ナレッジファイルがありません。</div>
                  ) : null}

                  {files.map((file) => (
                    <button
                      key={file.path}
                      type="button"
                      className={`knowledge-file-item ${selectedPath === file.path ? 'active' : ''}`}
                      onClick={() => void handleSelectFile(file.path)}
                    >
                      <div className="knowledge-file-icon">📄</div>
                      <div className="knowledge-file-info">
                        <div className="knowledge-file-name">{file.name}</div>
                        <div className="knowledge-file-meta">
                          {formatBytes(file.size)} · {formatDate(file.modified)}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                <div className="knowledge-detail-panel">
                  {detailLoading ? (
                    <div className="knowledge-empty-state">
                      <div className="spinner" />
                      <p>ファイルを読み込み中…</p>
                    </div>
                  ) : selectedFile ? (
                    <>
                      <div className="knowledge-detail-header">
                        <div className="knowledge-detail-title-wrap">
                          <h3>{selectedFile.name}</h3>
                          <div className="knowledge-file-meta">
                            {selectedFile.path} · {formatBytes(selectedFile.size)} · {formatDate(selectedFile.modified)}
                          </div>
                        </div>
                        <div className="knowledge-detail-actions">
                          {!isEditing ? (
                            <>
                              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setIsEditing(true)}>
                                編集
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-danger"
                                onClick={handleDelete}
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
                                onClick={handleSave}
                                disabled={saving}
                              >
                                保存
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                  setIsEditing(false)
                                  setEditContent(selectedFile.content)
                                }}
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
                        />
                      ) : (
                        <pre className="knowledge-preview">{selectedFile.content || '内容がありません。'}</pre>
                      )}
                    </>
                  ) : (
                    <div className="knowledge-empty-state">
                      <FileText size={28} className="empty-state-icon" />
                      <h3>ファイルを選択してください</h3>
                      <p>左側の一覧からナレッジファイルを選ぶと内容を確認できます。</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {showCreateModal ? (
        <div className="dialog-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="dialog knowledge-create-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-title">ナレッジファイルの新規作成</div>
            <div className="dialog-desc">knowledge ディレクトリに Markdown ファイルを追加します。</div>
            <div className="input-group">
              <label className="input-label" htmlFor="knowledge-file-name">
                ファイル名
              </label>
              <input
                id="knowledge-file-name"
                type="text"
                className="input"
                placeholder="例: my_knowledge.md"
                value={newFileName}
                onChange={(event) => setNewFileName(event.target.value)}
              />
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
              />
            </div>
            <div className="dialog-actions">
              <button type="button" className="btn btn-primary" onClick={handleCreate} disabled={creating}>
                作成
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>
                キャンセル
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
