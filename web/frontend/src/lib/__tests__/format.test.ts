import { describe, expect, it } from 'vitest'

import { formatDateTime, formatNumber, formatScore, formatYen } from '../utils'

describe('formatters', () => {
  it('formatDateTime は null/空/不正値を「—」にする', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('')).toBe('—')
    // 不正な日付文字列は元文字列を返す（生ISO崩れの可視化）
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
  })

  it('formatDateTime は有効な日時を年月日時分で返す', () => {
    const out = formatDateTime('2026-06-14T09:05:00Z')
    expect(out).not.toBe('—')
    expect(out).toMatch(/2026/)
  })

  it('formatNumber は千区切り、不正値は「—」', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
  })

  it('formatYen は円表記で四捨五入', () => {
    expect(formatYen(1234.6)).toBe('¥1,235')
    expect(formatYen(null)).toBe('—')
  })

  it('formatScore は既定0桁、digits 指定可', () => {
    expect(formatScore(82.49)).toBe('82')
    expect(formatScore(82.49, 1)).toBe('82.5')
    expect(formatScore(undefined)).toBe('—')
  })
})
