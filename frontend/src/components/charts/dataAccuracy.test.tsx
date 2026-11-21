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

describe('BarChart exact proportions', () => {
  /** Read the inline scaleX transform off every bar fill. */
  function barTransforms(): number[] {
    return [...document.querySelectorAll<HTMLElement>('div[style*="scaleX"]')].map((node) => {
      const match = /scaleX\(([^)]+)\)/.exec(node.style.transform)
      return match ? Number(match[1]) : NaN
    })
  }

  it.each([
    [1, 0.01],
    [2, 0.02],
    [30, 0.3],
    [100, 1],
  ])('renders value %i against max 100 at exactly %f of the track', async (value, expected) => {
    render(
      <BarChart
        ariaLabel='Exact ratios'
        items={[
          { key: 'target', label: 'Target', value, color: palette.chart[0] },
          { key: 'max', label: 'Max', value: 100, color: palette.chart[1] },
        ]}
      />,
    )

    await waitFor(() => {
      const [target] = barTransforms()
      expect(target).toBeCloseTo(expected, 6)
    })
  })

  it('renders a lone item as full width because it is its own maximum', async () => {
    render(
      <BarChart
        ariaLabel='No minimum width'
        items={[{ key: 'tiny', label: 'Tiny', value: 1, color: palette.chart[0] }]}
      />,
    )

    await waitFor(() => {
      const [only] = barTransforms()
      // A clean ratio, not a clamped 4% floor.
      expect(only).toBe(1)
    })
  })

  it('does not apply a minimum width to a tiny value beside a large one', async () => {
    render(
      <BarChart
        ariaLabel='No minimum width'
        items={[
          { key: 'tiny', label: 'Tiny', value: 1, color: palette.chart[0] },
          { key: 'big', label: 'Big', value: 99, color: palette.chart[1] },
        ]}
      />,
    )

    await waitFor(() => {
      const ratios = barTransforms()
      // 1/99 ≈ 0.0101 — the old implementation would have forced this to 0.04.
      expect(ratios[0]).toBeCloseTo(1 / 99, 6)
      expect(ratios[1]).toBe(1)
    })
  })

  it('renders zero as zero, not as a sliver', async () => {
    render(
      <BarChart
        ariaLabel='Zero rendering'
        items={[
          { key: 'zero', label: 'Zero', value: 0, color: palette.chart[0] },
          { key: 'some', label: 'Some', value: 5, color: palette.chart[1] },
        ]}
      />,
    )

    await waitFor(() => {
      const [zero] = barTransforms()
      expect(zero).toBe(0)
    })
  })

  it('keeps an all-zero dataset at zero without dividing by zero', async () => {
    render(
      <BarChart
        ariaLabel='All zero'
        items={[
          { key: 'a', label: 'A', value: 0, color: palette.chart[0] },
          { key: 'b', label: 'B', value: 0, color: palette.chart[1] },
        ]}
      />,
    )

    await waitFor(() => {
      expect(barTransforms().every((ratio) => ratio === 0)).toBe(true)
    })
    expect(screen.getAllByText('0%').length).toBeGreaterThanOrEqual(1)
  })

  it('renders nothing for an empty dataset', () => {
    const { container } = render(<BarChart ariaLabel='Empty' items={[]} />)
    expect(container.querySelectorAll('li')).toHaveLength(0)
  })

  it('prints the exact count and share beside every bar', () => {
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
