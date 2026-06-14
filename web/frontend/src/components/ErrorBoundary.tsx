import { AlertTriangle } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode; fallback?: ReactNode }
type State = { error: Error | null }

/**
 * アプリ全体（および任意セクション）を包むエラーバウンダリ。
 *
 * API 応答の形ズレ（null/欠落/型違い）で `.map`/`.join` 等が例外を投げても、画面全体の
 * ホワイトアウトを防ぎ、回復導線（再読み込み）を出す。生成系・外部送信は一切行わない。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 診断用にコンソールへ残す（外部送信なし）。
    console.error('ErrorBoundary caught an error', error, info)
  }

  private handleReload = (): void => {
    this.setState({ error: null })
    if (typeof window !== 'undefined') window.location.reload()
  }

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="error-boundary" role="alert">
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <AlertTriangle className="empty-state-icon" size={28} />
                <h3>画面の表示中に問題が発生しました</h3>
                <p>
                  一時的なデータの不整合が原因の可能性があります。再読み込みで回復することがあります。
                </p>
                <pre className="error-boundary-detail">{this.state.error.message}</pre>
                <button type="button" className="btn btn-primary" onClick={this.handleReload}>
                  再読み込み
                </button>
              </div>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
