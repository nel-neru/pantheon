import { act } from 'react'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GoalsPage } from '../GoalsPage'
import { mockStreamSSE } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

// streamSse のモック実装ヘルパー。
// events 配列内の各オブジェクトを onEvent に順に渡し、最後に resolve する。
function makeStreamMock(events: Record<string, unknown>[]) {
  return vi.fn().mockImplementation(
    async (
      _path: string,
      _body: unknown,
      onEvent: (ev: Record<string, unknown>) => void,
      _signal?: AbortSignal,
    ) => {
      for (const ev of events) {
        onEvent(ev)
      }
    },
  )
}

const startEvent = {
  type: 'start',
  goal: 'コードの品質を改善する',
  org_name: 'TestOrg',
}

const progressEvent1 = {
  type: 'progress',
  done: 1,
  total: 3,
  failed: 0,
  progress_pct: 33.3,
  message: 'タスク 1 完了',
  content: '',
}

const progressEvent2 = {
  type: 'progress',
  done: 3,
  total: 3,
  failed: 0,
  progress_pct: 100,
  message: 'タスク 3 完了',
  content: '',
}

const resultEvent = {
  type: 'result',
  goal: 'コードの品質を改善する',
  org_name: 'TestOrg',
  result: '品質改善提案を作成しました。',
  summary: '3つのタスクを完了しました。',
  content: '',
  data: {},
}

const doneEvent = {
  type: 'done',
  goal: 'コードの品質を改善する',
  org_name: 'TestOrg',
  result: '品質改善提案を作成しました。',
  content: '',
}

describe('GoalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamSSE.mockReset()
  })

  it('初期状態でテキストエリアと実行ボタンが表示される', () => {
    renderWithRouter(<GoalsPage />)

    expect(screen.getByRole('textbox', { name: 'ゴールテキスト' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '実行' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '実行' })).toBeDisabled()
  })

  it('テキストが空のとき実行ボタンは無効', () => {
    renderWithRouter(<GoalsPage />)

    const button = screen.getByRole('button', { name: '実行' })
    expect(button).toBeDisabled()
  })

  it('テキスト入力後に実行ボタンが有効になる', async () => {
    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    const textarea = screen.getByRole('textbox', { name: 'ゴールテキスト' })
    await user.type(textarea, 'テストゴール')

    expect(screen.getByRole('button', { name: '実行' })).toBeEnabled()
  })

  it('実行中はボタンが無効になり中止ボタンが現れる', async () => {
    // streamSse が解決するまで待機するモック
    let resolveStream!: () => void
    mockStreamSSE.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        _onEvent: (ev: Record<string, unknown>) => void,
        _signal?: AbortSignal,
      ) => {
        await new Promise<void>((resolve) => {
          resolveStream = resolve
        })
      },
    )

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), 'テストゴール')
    await user.click(screen.getByRole('button', { name: '実行' }))

    // 実行中はボタン無効 + 中止ボタン表示
    expect(screen.getByRole('button', { name: '実行中…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '中止' })).toBeInTheDocument()

    // テスト後に必ず解決
    resolveStream()
  })

  it('start → progress × 2 → result → done の正常系フローを描画する', async () => {
    mockStreamSSE.mockImplementation(makeStreamMock([
      startEvent,
      progressEvent1,
      progressEvent2,
      resultEvent,
      doneEvent,
    ]))

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(
      screen.getByRole('textbox', { name: 'ゴールテキスト' }),
      'コードの品質を改善する',
    )
    await user.click(screen.getByRole('button', { name: '実行' }))

    // 最終結果が表示される
    expect(await screen.findByText('品質改善提案を作成しました。')).toBeInTheDocument()
    expect(screen.getByText('3つのタスクを完了しました。')).toBeInTheDocument()
    expect(screen.getByText('完了')).toBeInTheDocument()
  })

  it('progress イベントで 1/3 のカウントが表示される', async () => {
    // progress1 の時点でブロックするモック
    let resolveStream!: () => void
    mockStreamSSE.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        onEvent: (ev: Record<string, unknown>) => void,
        _signal?: AbortSignal,
      ) => {
        onEvent(startEvent)
        onEvent(progressEvent1)
        await new Promise<void>((resolve) => {
          resolveStream = resolve
        })
      },
    )

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(
      screen.getByRole('textbox', { name: 'ゴールテキスト' }),
      'コードの品質を改善する',
    )
    await user.click(screen.getByRole('button', { name: '実行' }))

    // 進捗カウント 1/3 が表示される
    expect(await screen.findByText('1/3')).toBeInTheDocument()
    // プログレスバーがある
    expect(screen.getByRole('progressbar', { name: '進捗' })).toBeInTheDocument()

    resolveStream()
  })

  it('error イベントでエラーメッセージが表示される', async () => {
    const errorEvent = {
      type: 'error',
      message: 'エージェントの起動に失敗しました。',
    }

    mockStreamSSE.mockImplementation(makeStreamMock([startEvent, errorEvent]))

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), 'テストゴール')
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(await screen.findByText('エージェントの起動に失敗しました。')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('中止ボタンをクリックするとアイドル状態に戻る', async () => {
    let resolveStream!: () => void
    mockStreamSSE.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        _onEvent: (ev: Record<string, unknown>) => void,
        _signal?: AbortSignal,
      ) => {
        await new Promise<void>((resolve) => {
          resolveStream = resolve
        })
      },
    )

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), 'テストゴール')
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(screen.getByRole('button', { name: '中止' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '中止' }))

    // 中止後はアイドル → 実行ボタンが戻る
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '実行' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '中止' })).not.toBeInTheDocument()

    resolveStream()
  })

  it('streamSse が AbortError を throw しても エラー表示しない（中止扱い）', async () => {
    mockStreamSSE.mockImplementation(async () => {
      const err = new Error('AbortError')
      err.name = 'AbortError'
      throw err
    })

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), 'テストゴール')
    await user.click(screen.getByRole('button', { name: '実行' }))

    // エラーカードではなくアイドル状態に戻る
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '実行' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('streamSse が通常エラーを throw するとエラー表示する', async () => {
    mockStreamSSE.mockImplementation(async () => {
      throw new Error('接続に失敗しました。')
    })

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), 'テストゴール')
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(await screen.findByText('接続に失敗しました。')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('スペースのみのテキストは実行不可（whitespace guard）', async () => {
    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(screen.getByRole('textbox', { name: 'ゴールテキスト' }), '   ')

    expect(screen.getByRole('button', { name: '実行' })).toBeDisabled()
    expect(mockStreamSSE).not.toHaveBeenCalled()
  })

  it('中止後に到着した遅延イベントは状態を汚染しない（W1 stale-run guard）', async () => {
    // モックは onEvent と signal を捕捉し、start/progress を流して promise でブロックする。
    // 中止後に「遅れて届いた result」を手動で発火させ、ガードが破棄することを検証する。
    let capturedOnEvent!: (ev: Record<string, unknown>) => void
    let resolveStream!: () => void
    mockStreamSSE.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        onEvent: (ev: Record<string, unknown>) => void,
        _signal?: AbortSignal,
      ) => {
        capturedOnEvent = onEvent
        onEvent(startEvent)
        onEvent(progressEvent1)
        await new Promise<void>((resolve) => {
          resolveStream = resolve
        })
      },
    )

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(
      screen.getByRole('textbox', { name: 'ゴールテキスト' }),
      'コードの品質を改善する',
    )
    await user.click(screen.getByRole('button', { name: '実行' }))
    expect(await screen.findByText('1/3')).toBeInTheDocument()

    // 中止 → アイドルへ
    await user.click(screen.getByRole('button', { name: '中止' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '実行' })).toBeInTheDocument()
    })

    // 中止後に遅延 result イベントが到着しても、結果カードを描画してはならない。
    act(() => {
      capturedOnEvent(resultEvent)
    })
    expect(screen.queryByText('品質改善提案を作成しました。')).not.toBeInTheDocument()
    expect(screen.queryByText('完了')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '実行' })).toBeInTheDocument()

    resolveStream()
  })

  it('failed > 0 のとき失敗カウントが表示される', async () => {
    const progressWithFailed = {
      type: 'progress',
      done: 2,
      total: 3,
      failed: 1,
      progress_pct: 66.6,
      message: '進行中',
      content: '',
    }

    let resolveStream!: () => void
    mockStreamSSE.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        onEvent: (ev: Record<string, unknown>) => void,
        _signal?: AbortSignal,
      ) => {
        onEvent(startEvent)
        onEvent(progressWithFailed)
        await new Promise<void>((resolve) => {
          resolveStream = resolve
        })
      },
    )

    const user = userEvent.setup()
    renderWithRouter(<GoalsPage />)

    await user.type(
      screen.getByRole('textbox', { name: 'ゴールテキスト' }),
      'コードの品質を改善する',
    )
    await user.click(screen.getByRole('button', { name: '実行' }))

    expect(await screen.findByText('2/3')).toBeInTheDocument()
    expect(screen.getByText('（失敗 1）')).toBeInTheDocument()

    resolveStream()
  })
})

// streamSse の単体テスト（src/lib/api.ts の実装検証）
// チャンク境界をまたぐ部分フレームのバッファリングを検証する
describe('streamSse ユーティリティ（fetch モック）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('2チャンクにまたがった SSE フレームを正しくパースできる', async () => {
    // このテストは実際の streamSse 実装を呼ぶため、@/lib/api モックを使わず
    // global.fetch をモックする
    const { streamSse: realStreamSse } = await vi.importActual<typeof import('@/lib/api')>(
      '@/lib/api',
    )

    const encoder = new TextEncoder()
    // フレームを2チャンクに分割: "data: {...}\n" + "\n"
    const fullFrame = 'data: {"type":"start","goal":"test","org_name":null}\n\n'
    const chunk1 = fullFrame.slice(0, fullFrame.length - 1)
    const chunk2 = fullFrame.slice(fullFrame.length - 1)

    let callCount = 0
    const fakeReader = {
      read: vi.fn().mockImplementation(async () => {
        callCount++
        if (callCount === 1) return { done: false, value: encoder.encode(chunk1) }
        if (callCount === 2) return { done: false, value: encoder.encode(chunk2) }
        return { done: true, value: undefined }
      }),
      releaseLock: vi.fn(),
    }

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => fakeReader },
      }),
    )

    const events: Record<string, unknown>[] = []
    await realStreamSse('/api/goals/stream', { goal_text: 'test' }, (ev) => {
      events.push(ev)
    })

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({ type: 'start', goal: 'test' })

    vi.unstubAllGlobals()
  })

  it('複数フレームが1チャンクに含まれていても全て処理できる', async () => {
    const { streamSse: realStreamSse } = await vi.importActual<typeof import('@/lib/api')>(
      '@/lib/api',
    )

    const encoder = new TextEncoder()
    const twoFrames =
      'data: {"type":"start","goal":"g","org_name":null}\n\n' +
      'data: {"type":"done","goal":"g","org_name":null,"result":"ok","content":""}\n\n'

    let callCount = 0
    const fakeReader = {
      read: vi.fn().mockImplementation(async () => {
        callCount++
        if (callCount === 1) return { done: false, value: encoder.encode(twoFrames) }
        return { done: true, value: undefined }
      }),
      releaseLock: vi.fn(),
    }

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader: () => fakeReader },
      }),
    )

    const events: Record<string, unknown>[] = []
    await realStreamSse('/api/goals/stream', { goal_text: 'g' }, (ev) => {
      events.push(ev)
    })

    expect(events).toHaveLength(2)
    expect(events[0]).toMatchObject({ type: 'start' })
    expect(events[1]).toMatchObject({ type: 'done', result: 'ok' })

    vi.unstubAllGlobals()
  })
})
