import { fireEvent, render as rtlRender, screen } from '@testing-library/react'
import { ChakraProvider } from '@chakra-ui/react'
import { describe, expect, it, vi } from 'vite-plus/test'

import { Pagination } from './Pagination.tsx'
import { system } from '../theme/system.ts'

function render(ui: React.ReactElement) {
  return rtlRender(ui, {
    wrapper: ({ children }) => <ChakraProvider value={system}>{children}</ChakraProvider>,
  })
}

function fullProps(overrides: Partial<Parameters<typeof Pagination>[0]> = {}) {
  return {
    page: 1,
    pageSize: 20,
    total: 300,
    totalPages: 15,
    onPageChange: vi.fn(),
    ...overrides,
  }
}

/**
 * The UI contract from the bug report: circular navigation proven at the
 * component boundary, using only valid page numbers.
 */
describe('Pagination circular navigation', () => {
  it('Next from the last page wraps to page 1', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 15, onPageChange })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })

  it('Previous from page 1 wraps to the last page', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 1, onPageChange })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(onPageChange).toHaveBeenCalledWith(15)
  })

  it('Next advances by one in the middle', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 5, onPageChange })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(6)
  })

  it('only renders real page numbers', () => {
    render(<Pagination {...fullProps({ page: 8, totalPages: 15 })} />)
    for (const button of screen.getAllByRole('button', { name: /^Page \d+$/ })) {
      const page = Number(button.textContent)
      expect(page).toBeGreaterThanOrEqual(1)
      expect(page).toBeLessThanOrEqual(15)
    }
  })

  it('marks the current page with aria-current', () => {
    render(<Pagination {...fullProps({ page: 4 })} />)
    expect(screen.getByRole('button', { name: 'Page 4' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('navigates when a visible page number is clicked', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 4, onPageChange })} />)
    // Page 5 is inside the window around page 4.
    fireEvent.click(screen.getByRole('button', { name: 'Page 5' }))
    expect(onPageChange).toHaveBeenCalledWith(5)
  })
})

describe('Pagination edge cases', () => {
  it('disables navigation for a single page', () => {
    render(<Pagination {...fullProps({ page: 1, total: 8, totalPages: 1 })} />)
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
  })

  it('disables navigation for an empty result set', () => {
    render(<Pagination {...fullProps({ page: 1, total: 0, totalPages: 1 })} />)
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
  })

  it('shows "No tickets" when the total is zero', () => {
    render(<Pagination {...fullProps({ total: 0, totalPages: 1 })} />)
    expect(screen.getByText('No tickets')).toBeInTheDocument()
  })

  it('shows the real range and total for a partial last page', () => {
    render(<Pagination {...fullProps({ page: 2, total: 21, totalPages: 2 })} />)
    // 21 total, 20 per page -> page 2 covers 21-21. There are two "21" spans
    // (range start and end), all within the "Showing 21-21 of 21" summary.
    const summary = screen.getByText(/Showing/i)
    expect(summary.textContent).toContain('21')
    expect(summary.textContent).toContain('of')
  })

  it('does not fire navigation while a page is loading', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 3, isLoading: true, onPageChange })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(onPageChange).not.toHaveBeenCalled()
  })

  it('does not report a change when clicking the current page number', () => {
    const onPageChange = vi.fn()
    render(<Pagination {...fullProps({ page: 3, onPageChange })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    expect(onPageChange).not.toHaveBeenCalled()
  })
})

describe('Pagination legacy mode', () => {
  it('disables Previous on page 1 and Next when there is no next page', () => {
    render(
      <Pagination page={1} pageSize={20} itemCount={5} hasNext={false} onPageChange={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
  })

  it('advances by one when a next page is known', () => {
    const onPageChange = vi.fn()
    render(
      <Pagination page={2} pageSize={20} itemCount={20} hasNext onPageChange={onPageChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })
})
