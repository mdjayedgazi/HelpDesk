import { ChakraProvider } from '@chakra-ui/react'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vite-plus/test'
import { MemoryRouter } from 'react-router-dom'

import { BarChart } from './BarChart.tsx'
import { Sparkline } from './Sparkline.tsx'
import { MetricCard } from '../MetricCard.tsx'
import { palette } from '../../theme/palette.ts'
import { system } from '../../theme/system.ts'

/**
 * Regression guards for the "make the data move, not the data lie" rule.
 *
 * Every animated mark has to rest at a value derived from the props it was
 * given. These tests read the final geometry/ARIA state rather than the
 * in-flight frames.
 */

function render(ui: ReactElement) {
  return rtlRender(ui, {
    wrapper: ({ children }) => (
      <ChakraProvider value={system}>
        <MemoryRouter>{children}</MemoryRouter>
      </ChakraProvider>
    ),
  })
}

describe('BarChart proportionality', () => {
  it('scales each bar to its share of the largest value', async () => {
    render(
      <BarChart
        ariaLabel='Tickets by priority'
        items={[
          { key: 'LOW', label: 'Low', value: 2, color: palette.chart[0] },
          { key: 'NORMAL', label: 'Normal', value: 8, color: palette.chart[1] },
          { key: 'URGENT', label: 'Urgent', value: 0, color: palette.chart[4] },
        ]}
      />,
    )

    // Bars are scaleX transforms of a full-width track.
    await waitFor(() => {
      const transforms = [...document.querySelectorAll<HTMLElement>('div[style*="scaleX"]')].map(
        (node) => node.style.transform,
      )
      expect(transforms).toContain('scaleX(0.25)')
      expect(transforms).toContain('scaleX(1)')
    })
  })

  it('prints the real count and share beside every bar', () => {
    render(
      <BarChart
        ariaLabel='Tickets by priority'
        items={[
          { key: 'LOW', label: 'Low', value: 2, color: palette.chart[0] },
          { key: 'NORMAL', label: 'Normal', value: 8, color: palette.chart[1] },
        ]}
      />,
    )

    // 2 of 10 and 8 of 10. Each percentage exists in the visible row and in
    // the accessible data table, so both are asserted rather than one.
    expect(screen.getAllByText('20%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('80%').length).toBeGreaterThanOrEqual(1)
    // The accessible table carries the same numbers.
    expect(screen.getAllByRole('table', { hidden: true }).length).toBe(1)
  })
})

describe('MetricCard value accuracy', () => {
  it('settles a numeric metric on the exact backend value', async () => {
    render(<MetricCard label='Open tickets' value={30} />)

    await waitFor(() => {
      const animated = document.querySelector('[aria-hidden="true"]')
      expect(animated?.textContent).toBe('30')
    })
  })

  it('does not animate a loading placeholder into a number', () => {
    render(<MetricCard label='Open tickets' value='—' />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('formats large values consistently with the animation', async () => {
    render(<MetricCard label='Total tickets' value={1284} />)
    await waitFor(() => {
      const animated = document.querySelector('[aria-hidden="true"]')
      expect(animated?.textContent).toBe('1,284')
    })
  })
})

describe('Sparkline', () => {
  it('renders nothing for a single point instead of inventing a trend', () => {
    const { container } = render(<Sparkline values={[3]} color={palette.chart[0]} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('leaves the line drawn (fully visible) after its entrance', async () => {
    render(<Sparkline values={[1, 4, 2, 6]} color={palette.chart[0]} />)
    const line = document.querySelector('svg path[stroke]') as SVGPathElement | null
    expect(line).not.toBeNull()
    await waitFor(() => {
      expect(line!.style.strokeDashoffset).toBe('0')
    })
  })
})
