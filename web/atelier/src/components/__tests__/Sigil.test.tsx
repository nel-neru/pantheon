import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'

import { Sigil } from '../Sigil'

describe('Sigil', () => {
  it('renders an svg with deterministic geometry for a seed', () => {
    const { container, rerender } = render(<Sigil seed="hermes" />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    const firstPath = container.querySelector('path')?.getAttribute('d')

    rerender(<Sigil seed="hermes" />)
    const samePath = container.querySelector('path')?.getAttribute('d')
    expect(samePath).toBe(firstPath)
  })

  it('produces different geometry for different seeds', () => {
    const a = render(<Sigil seed="apollo" />).container.querySelector('path')?.getAttribute('d')
    const b = render(<Sigil seed="athena" />).container.querySelector('path')?.getAttribute('d')
    expect(a).not.toBe(b)
  })
})
