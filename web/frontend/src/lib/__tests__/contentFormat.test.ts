import { describe, expect, it } from 'vitest'

import { countChars, readingStats, splitIntoThread, X_LIMIT } from '../contentFormat'

describe('countChars', () => {
  it('コードポイント単位で数える（絵文字は1）', () => {
    expect(countChars('abc')).toBe(3)
    expect(countChars('😀😀')).toBe(2)
  })
})

describe('splitIntoThread', () => {
  it('空文字は空配列', () => {
    expect(splitIntoThread('   ')).toEqual([])
  })

  it('上限以内なら1件のまま（番号を付けない）', () => {
    const text = '短い投稿です。'
    expect(splitIntoThread(text)).toEqual([text])
  })

  it('上限超過は複数の番号付きツイートに分割する', () => {
    const sentence = 'これはとても長い文章のテストです。'
    const long = sentence.repeat(40) // 280字を大きく超える
    const thread = splitIntoThread(long)
    expect(thread.length).toBeGreaterThan(1)
    // 各ツイートが上限以内
    for (const tweet of thread) {
      expect(countChars(tweet)).toBeLessThanOrEqual(X_LIMIT)
    }
    // 末尾に (i/n) 番号が付く
    expect(thread[0]).toMatch(/\(1\/\d+\)$/)
    expect(thread[thread.length - 1]).toMatch(new RegExp(`\\(${thread.length}/${thread.length}\\)$`))
  })

  it('区切りの無い超長文も上限内にハードラップする', () => {
    const long = 'あ'.repeat(1000)
    const thread = splitIntoThread(long)
    for (const tweet of thread) {
      expect(countChars(tweet)).toBeLessThanOrEqual(X_LIMIT)
    }
  })

  it('100チャンク超でも全チャンク（接尾辞込み）が X_LIMIT 以下', () => {
    // 100 チャンクを確実に超えるよう、ユニット境界なしの連続テキストを使う。
    // 区切り文字なし・270字/チャンク × 120 チャンク分 = ~32400字
    const long = 'a'.repeat(270 * 120)
    const thread = splitIntoThread(long)
    expect(thread.length).toBeGreaterThan(100)
    for (const tweet of thread) {
      expect(countChars(tweet)).toBeLessThanOrEqual(X_LIMIT)
    }
    // 末尾チャンクの番号が3桁以上であることを確認
    expect(thread[thread.length - 1]).toMatch(/\(\d{3,}\/\d{3,}\)$/)
  })
})

describe('readingStats', () => {
  it('文字数・行数・概算読了時間を返す', () => {
    const stats = readingStats('一行目\n二行目')
    expect(stats.chars).toBe(7)
    expect(stats.lines).toBe(2)
    expect(stats.minutes).toBeGreaterThanOrEqual(1)
  })
})
