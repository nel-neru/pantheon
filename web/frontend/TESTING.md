# Frontend Testing Guide

## テスト構成

- **フレームワーク**: Vitest + React Testing Library
- **テストファイル配置**: `src/pages/__tests__/<PageName>.test.tsx`
- **設定ファイル**: `vite.config.ts` の `test` セクション
- **セットアップ**: `src/test/setup.ts`

## テストの実行

```bash
# 全テスト実行
npm test

# ウォッチモード
npm run test:watch

# カバレッジレポート
npm run test:coverage
```

## 新しいページを追加するとき

1. `src/pages/NewPage.tsx` を作成する
2. **必ず** `src/pages/__tests__/NewPage.test.tsx` も作成する
3. テストには以下を含めること:
   - レンダリングテスト（コンポーネントが表示されること）
   - ローディング状態テスト
   - 空状態テスト（APIがデータなしを返す場合）
   - エラー状態テスト（API失敗時）
   - 主要インタラクションテスト（ボタン・フォーム）

## ガード機能

`git commit` 時に `scripts/check_test_coverage.py` が自動実行されます。
ページファイルに対応するテストがない場合、コミットがブロックされます。

初回セットアップ:
```bash
bash scripts/install_hooks.sh
```

手動チェック:
```bash
python3 scripts/check_test_coverage.py
```

## API モックの書き方

```typescript
import { vi, beforeEach } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: vi.fn(),
  streamSSE: vi.fn(),
}))

import { api } from '@/lib/api'
const mockApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
})

it('データを表示する', async () => {
  mockApi.mockResolvedValueOnce([{ id: '1', name: 'Test' }])
  render(<MyPage />)
  await screen.findByText('Test')
})
```
