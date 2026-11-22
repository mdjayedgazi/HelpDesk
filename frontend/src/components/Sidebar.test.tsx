import { ChakraProvider } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vite-plus/test'

import { SidebarNav } from './Sidebar.tsx'
import { system } from '../theme/system.ts'

const sections = [
  {
    label: 'Overview',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: (() => <svg />) as never, end: true },
    ],
  },
  {
    label: 'Support',
    items: [{ label: 'Tickets', to: '/tickets', icon: (() => <svg />) as never }],
  },
]

function renderSidebar(compact: boolean) {
  return render(
    <ChakraProvider value={system}>
      <MemoryRouter>
        <SidebarNav sections={sections} compact={compact} />
      </MemoryRouter>
    </ChakraProvider>,
  )
}

/**
 * The compact (icon-rail) sidebar is used in the 1024–1279 px band. It must keep
 * every link's accessible name and never render the visible text label (which
 * would overflow the 64 px rail). These assertions guard that contract without
 * depending on CSS layout, which jsdom does not compute.
 */
describe('SidebarNav compact rail', () => {
  it('exposes an accessible name on each link in compact mode', () => {
    renderSidebar(true)
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Tickets' })).toBeInTheDocument()
  })

  it('adds a title affordance for pointer users in compact mode', () => {
    renderSidebar(true)
    const tickets = screen.getByRole('link', { name: 'Tickets' })
    expect(tickets).toHaveAttribute('title', 'Tickets')
  })

  it('renders the visible text label in full (non-compact) mode', () => {
    renderSidebar(false)
    // The label text node is present and visible (not the sr-only copy).
    const link = screen.getByRole('link', { name: 'Tickets' })
    expect(link).not.toHaveAttribute('title')
    expect(link.textContent).toContain('Tickets')
  })
})
