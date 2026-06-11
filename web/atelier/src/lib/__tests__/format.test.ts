import { describe, expect, it } from 'vitest'

import { clamp, compactNumber, pad2, percent, seedFrom } from '../format'

describe('format helpers', () => {
  it('pad2 zero-pads', () => {
    expect(pad2(3)).toBe('03')
    expect(pad2(42)).toBe('42')
  })

  it('compactNumber abbreviates', () => {
    expect(compactNumber(950)).toBe('950')
    expect(compactNumber(1500)).toBe('1.5k')
    expect(compactNumber(2_400_000)).toBe('2.4M')
  })

  it('percent handles fractions and whole numbers', () => {
    expect(percent(0.5)).toBe('50%')
    expect(percent(72)).toBe('72%')
  })

  it('seedFrom is deterministic and in range', () => {
    const a = seedFrom('alpha')
    const b = seedFrom('alpha')
    const c = seedFrom('beta')
    expect(a).toBe(b)
    expect(a).not.toBe(c)
    expect(a).toBeGreaterThanOrEqual(0)
    expect(a).toBeLessThan(1)
  })

  it('clamp bounds values', () => {
    expect(clamp(5, 0, 10)).toBe(5)
    expect(clamp(-3, 0, 10)).toBe(0)
    expect(clamp(99, 0, 10)).toBe(10)
  })
})
