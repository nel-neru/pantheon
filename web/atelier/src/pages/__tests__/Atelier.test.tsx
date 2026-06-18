import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import { Atelier } from '../Atelier'
import type { DesignStyle, Persona } from '@/lib/types'

// ---- fixtures ----------------------------------------------------------------

// 全パレット + typeface あり。
const styleFull: DesignStyle = {
  id: 'editorial',
  name: 'Editorial Noir',
  description: '余白と活字で語る、静かな高級感。',
  palette: { primary: '#101012', secondary: '#2a2a30', accent: '#c8a24a', background: '#f5f3ec' },
  font_family: 'Playfair Display',
}
// primary のみ + font_family 空文字 → スウォッチ1枚・typeface ブロック非表示。
const stylePartial: DesignStyle = {
  id: 'mono',
  name: 'Mono',
  description: '単色。',
  palette: { primary: '#ff0000' },
  font_family: '',
}
// パレット空 → fallback の単色 div（スウォッチ0枚）。
const styleEmptyPalette: DesignStyle = {
  id: 'void',
  name: 'Void',
  description: '色なし。',
  palette: {},
  font_family: '',
}

const personaFull: Persona = { id: 'sage', name: '賢者', role: '戦略アドバイザー' }
const personaNoRole: Persona = { id: 'ghost', name: '幽霊', role: '' }

// ---- mock ---------------------------------------------------------------------

type Resp =
  | { kind: 'ok'; data: unknown }
  | { kind: 'error'; detail: string }
  | { kind: 'pending' }

// /api/design-styles と /api/personas を URL で振り分け、各々 ok/error/pending を指定できる。
function mockApi(opts: { styles: Resp; personas: Resp }) {
  globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    const which = url.includes('/api/design-styles')
      ? opts.styles
      : url.includes('/api/personas')
        ? opts.personas
        : ({ kind: 'ok', data: [] } as Resp)
    if (which.kind === 'pending') return new Promise(() => {}) // 解決しない → loading 維持
    if (which.kind === 'error') {
      return Promise.resolve({
        ok: false,
        status: 500,
        statusText: 'err',
        json: async () => ({ detail: which.detail }),
      })
    }
    return Promise.resolve({ ok: true, json: async () => which.data })
  }) as unknown as typeof fetch
}

// ---- tests --------------------------------------------------------------------

describe('Atelier page', () => {
  it('happy path: マウントし、両 API のデータが実際にページへ流れる', async () => {
    mockApi({ styles: { kind: 'ok', data: [styleFull] }, personas: { kind: 'ok', data: [personaFull] } })
    render(<Atelier />)
    // マウント smoke（ページ identity）
    expect(screen.getByText('The Atelier')).toBeInTheDocument()
    // 両 useApi パイプラインが実データを描画する（load-bearing: API が壊れれば落ちる）
    await waitFor(() => expect(screen.getByText('Editorial Noir')).toBeInTheDocument())
    expect(screen.getByText('賢者')).toBeInTheDocument()
  })

  it('Design Styles 読込中は色見本セクションが Loading ラベルを出す', () => {
    mockApi({ styles: { kind: 'pending' }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    expect(screen.getByText(/色見本を展開/)).toBeInTheDocument()
  })

  it('Personas 読込中は声セクションが Loading ラベルを出す', () => {
    mockApi({ styles: { kind: 'ok', data: [] }, personas: { kind: 'pending' } })
    render(<Atelier />)
    expect(screen.getByText(/声を集める/)).toBeInTheDocument()
  })

  it('Design Styles エラー時は ErrorNote にバックエンドの detail を出す', async () => {
    mockApi({ styles: { kind: 'error', detail: 'スタイル取得失敗' }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('接続エラー')).toBeInTheDocument())
    expect(screen.getByText(/スタイル取得失敗/)).toBeInTheDocument()
  })

  it('Personas エラー時も ErrorNote に detail を出す', async () => {
    mockApi({ styles: { kind: 'ok', data: [] }, personas: { kind: 'error', detail: 'ペルソナ取得失敗' } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('接続エラー')).toBeInTheDocument())
    expect(screen.getByText(/ペルソナ取得失敗/)).toBeInTheDocument()
  })

  it('Design Styles が空配列なら EmptyState を出す', async () => {
    mockApi({ styles: { kind: 'ok', data: [] }, personas: { kind: 'ok', data: [personaFull] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('デザインスタイルがありません')).toBeInTheDocument())
  })

  it('Personas が空配列なら EmptyState と hint を出す', async () => {
    mockApi({ styles: { kind: 'ok', data: [styleFull] }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('ペルソナがありません')).toBeInTheDocument())
    expect(screen.getByText('config/personas に追加できます')).toBeInTheDocument()
  })

  it('スタイルを描画: 名前・typeface・全パレットスウォッチを render 順（primary→secondary→accent→background）で出す', async () => {
    mockApi({ styles: { kind: 'ok', data: [styleFull] }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('Editorial Noir')).toBeInTheDocument())
    // typeface ブロック（font_family あり）
    expect(screen.getByText('Playfair Display')).toBeInTheDocument()
    // 各スウォッチは aria-label="<slot> <color>" を持つ
    expect(screen.getByLabelText('primary #101012')).toBeInTheDocument()
    expect(screen.getByLabelText('secondary #2a2a30')).toBeInTheDocument()
    expect(screen.getByLabelText('accent #c8a24a')).toBeInTheDocument()
    expect(screen.getByLabelText('background #f5f3ec')).toBeInTheDocument()
    // paletteEntries の固定順を回帰検出（型の宣言順 ≠ render 順なので意味がある）
    const order = screen.getAllByLabelText(/#/).map((el) => el.getAttribute('aria-label'))
    expect(order).toEqual([
      'primary #101012',
      'secondary #2a2a30',
      'accent #c8a24a',
      'background #f5f3ec',
    ])
  })

  it('パレットが一部のみのスタイルは設定済みスロットのみスウォッチ化し、font_family 空なら typeface を出さない', async () => {
    mockApi({ styles: { kind: 'ok', data: [stylePartial] }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('Mono')).toBeInTheDocument())
    expect(screen.getByLabelText('primary #ff0000')).toBeInTheDocument()
    expect(screen.queryByLabelText(/secondary/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/accent/)).not.toBeInTheDocument()
    expect(screen.queryByText('typeface')).not.toBeInTheDocument()
  })

  it('パレット空のスタイルは fallback の単色になりスウォッチを1枚も出さない', async () => {
    mockApi({ styles: { kind: 'ok', data: [styleEmptyPalette] }, personas: { kind: 'ok', data: [] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('Void')).toBeInTheDocument())
    expect(screen.queryAllByLabelText(/#/)).toHaveLength(0)
  })

  it('ペルソナを描画: 名前・role・id を出す', async () => {
    mockApi({ styles: { kind: 'ok', data: [] }, personas: { kind: 'ok', data: [personaFull] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('賢者')).toBeInTheDocument())
    expect(screen.getByText('戦略アドバイザー')).toBeInTheDocument()
    expect(screen.getByText('sage')).toBeInTheDocument()
  })

  it('role 空のペルソナは "—" にフォールバックする', async () => {
    mockApi({ styles: { kind: 'ok', data: [] }, personas: { kind: 'ok', data: [personaNoRole] } })
    render(<Atelier />)
    await waitFor(() => expect(screen.getByText('幽霊')).toBeInTheDocument())
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
