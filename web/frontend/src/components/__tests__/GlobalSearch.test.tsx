import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GlobalSearch } from '@/components/GlobalSearch'
import { mockApi } from '@/test/mocks'
import { renderWithRouter } from '@/test/utils'

const RESULTS = [
  { id: 'o1', type: 'organization', title: 'Acme', subtitle: 'EC', route: '/orgs' },
  { id: 'a1', type: 'agent', title: 'Reviewer', subtitle: 'team', route: '/agents' },
]

describe('GlobalSearch (a11y)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  it('uses combobox/listbox ARIA roles', () => {
    renderWithRouter(<GlobalSearch />)
    const input = screen.getByRole('combobox', { name: '全体検索' })
    expect(input).toHaveAttribute('aria-expanded', 'false')
    expect(input).toHaveAttribute('aria-autocomplete', 'list')
  })

  it('does not search for queries shorter than 2 characters', async () => {
    renderWithRouter(<GlobalSearch />)
    await userEvent.type(screen.getByRole('combobox', { name: '全体検索' }), 'a')
    // 180ms 経過しても 1 文字では検索しない
    await new Promise((r) => setTimeout(r, 250))
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('fetches results and renders options with the first active', async () => {
    mockApi.mockResolvedValue(RESULTS)
    renderWithRouter(<GlobalSearch />)
    await userEvent.type(screen.getByRole('combobox', { name: '全体検索' }), 'org')

    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith('GET', expect.stringContaining('/api/search?q=org')),
    )
    const options = await screen.findAllByRole('option')
    expect(options).toHaveLength(2)
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    expect(options[1]).toHaveAttribute('aria-selected', 'false')
  })

  it('moves the active option with ArrowDown and selects with Enter', async () => {
    mockApi.mockResolvedValue(RESULTS)
    renderWithRouter(<GlobalSearch />)
    const input = screen.getByRole('combobox', { name: '全体検索' })
    await userEvent.type(input, 'org')
    await screen.findAllByRole('option')

    await userEvent.keyboard('{ArrowDown}')
    const options = screen.getAllByRole('option')
    expect(options[1]).toHaveAttribute('aria-selected', 'true')

    await userEvent.keyboard('{Enter}')
    // 選択後は入力がクリアされ、リストが閉じる
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
    expect(input).toHaveValue('')
  })

  it('closes the dropdown on Escape', async () => {
    mockApi.mockResolvedValue(RESULTS)
    renderWithRouter(<GlobalSearch />)
    const input = screen.getByRole('combobox', { name: '全体検索' })
    await userEvent.type(input, 'org')
    await screen.findAllByRole('option')

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
  })
})
