import { Link } from 'react-router-dom'

import { useApi } from '@/hooks/useApi'
import type { PlatformStatus } from '@/lib/types'

// グローバルバナー: claude CLI が未認証のときのみ表示する。
// fail-safe: loading 中・API エラー時・data が null のときは何も描画しない。
// 30秒ポーリングでユーザーが認証したらリロード無しでバナーが消える。
export function ClaudeStatusBanner() {
  const { data, loading, error } = useApi<PlatformStatus>('/api/platform/status', 30000)

  // fail-safe: 確定的に has_llm===false のときだけバナーを出す
  if (loading || error !== null || data === null || data.has_llm !== false) {
    return null
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="claude CLI 認証警告"
      className="claude-status-banner"
      style={{
        borderBottom: '1px solid var(--rose)',
        background: 'color-mix(in srgb, var(--rose) 10%, var(--ink-1))',
        padding: '10px clamp(24px, 5vw, 72px)',
      }}
    >
      <div
        style={{
          maxWidth: 'var(--page-max)',
          margin: '0 auto',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '12px',
        }}
      >
        <span
          className="kicker"
          style={{ color: 'var(--rose)', letterSpacing: '0.22em' }}
        >
          claude CLI が未認証です
        </span>
        <span className="text-dim" style={{ fontSize: 13 }}>
          Pantheon の生成機能はローカルの{' '}
          <code
            className="mono"
            style={{ fontSize: 12, color: 'var(--text)', background: 'var(--ink-3)', padding: '1px 5px', borderRadius: 4, border: '1px solid var(--line)' }}
          >
            claude
          </code>{' '}
          CLI 経由で動きます（API キーは不要）。ターミナルで{' '}
          <code
            className="mono"
            style={{ fontSize: 12, color: 'var(--text)', background: 'var(--ink-3)', padding: '1px 5px', borderRadius: 4, border: '1px solid var(--line)' }}
          >
            claude
          </code>{' '}
          を一度実行してログインしてください。
        </span>
        <Link
          to="/handbook"
          className="mono"
          style={{ fontSize: 11, color: 'var(--rose)', letterSpacing: '0.16em', textDecoration: 'underline', textUnderlineOffset: 3, whiteSpace: 'nowrap' }}
        >
          セットアップ手順を見る
        </Link>
      </div>
    </div>
  )
}
