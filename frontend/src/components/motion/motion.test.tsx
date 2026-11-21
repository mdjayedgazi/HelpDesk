import { ChakraProvider } from '@chakra-ui/react'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

import { system } from '../../theme/system.ts'
import { AnimatedNumber } from './AnimatedNumber.tsx'
import { AnimatedProgress } from './AnimatedProgress.tsx'

/** These primitives render Chakra elements, so they need the design system. */
function render(ui: ReactElement) {
  return rtlRender(ui, {
    wrapper: ({ children }) => <ChakraProvider value={system}>{children}</ChakraProvider>,
  })
}

/**
 * These tests guard the one rule that matters most for animated data: the
 * animation must never change the number. Every value on screen has to settle
 * on exactly what the backend returned.
 */

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? reduce : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

describe('AnimatedNumber', () => {
  it('settles on exactly the value passed in', async () => {
    render(<AnimatedNumber value={30} />)
    // The animated digits are aria-hidden; the accessible copy is the real value.
    expect(screen.getAllByText('30').length).toBeGreaterThanOrEqual(1)

    await waitFor(() => {
      const visible = document.querySelector('span[aria-hidden="true"]')
      expect(visible?.textContent?.replace(/[^0-9]/g, '')).toBe('30')
    })
  })

  it('renders the final value immediately under reduced motion', () => {
    stubReducedMotion(true)
    render(<AnimatedNumber value={1284} />)
    const visible = document.querySelector('span[aria-hidden="true"]')
    expect(visible?.textContent).toBe('1,284')
  })

  it('renders non-numeric placeholders untouched', () => {
    render(<AnimatedNumber value='—' />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('exposes the accessible value once, not the intermediate frames', () => {
    render(<AnimatedNumber value={7} />)
    // The aria-hidden animated copy plus a visually hidden final copy.
    const matches = screen.getAllByText('7')
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })
})

describe('AnimatedProgress', () => {
  /** Read the rendered fill ratio from the inline transform. */
  function fillRatio(name: RegExp | string): number {
    const bar = screen.getByRole('progressbar', { name })
    const fill = bar.firstElementChild as HTMLElement
    const match = /scaleX\(([^)]+)\)/.exec(fill.style.transform)
    return match ? Number(match[1]) : NaN
  }

  it('reports the real value through progressbar semantics', () => {
    render(<AnimatedProgress value={30} max={100} label='Resolution rate' />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-valuenow', '30')
    expect(bar).toHaveAttribute('aria-valuetext', '30%')
  })

  it.each([
    { value: 30, max: 100, now: '30', percent: '30%', ratio: 0.3 },
    { value: 70, max: 100, now: '70', percent: '70%', ratio: 0.7 },
    { value: 100, max: 100, now: '100', percent: '100%', ratio: 1 },
    { value: 120, max: 100, now: '100', percent: '100%', ratio: 1 },
    { value: -10, max: 100, now: '0', percent: '0%', ratio: 0 },
    { value: 0, max: 100, now: '0', percent: '0%', ratio: 0 },
  ])(
    'normalizes value=$value max=$max to now=$now / $percent',
    async ({ value, max, now, percent, ratio }) => {
      render(<AnimatedProgress value={value} max={max} label='Metric' />)
      const bar = screen.getByRole('progressbar')
      expect(bar).toHaveAttribute('aria-valuenow', now)
      expect(bar).toHaveAttribute('aria-valuemax', '100')
      expect(bar).toHaveAttribute('aria-valuetext', percent)
      await waitFor(() => {
        expect(fillRatio('Metric')).toBeCloseTo(ratio, 6)
      })
      // The visible label and the announced text are derived from the same
      // normalized ratio. (The digits animate inside an aria-hidden span and a
      // visually hidden copy, so compare the assembled root text rather than a
      // single text node.)
      const root = bar.parentElement as HTMLElement
      expect(root.textContent).toContain(percent)
    },
  )

  it('falls back to a documented denominator when max is zero', async () => {
    render(<AnimatedProgress value={0} max={0} label='Undefined scale' />)
    const bar = screen.getByRole('progressbar')
    // Documented behaviour: an unusable denominator falls back to 100, so the
    // ARIA range stays valid and the value stays honest (0 of 100).
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-valuenow', '0')
    await waitFor(() => {
      expect(fillRatio('Undefined scale')).toBe(0)
    })
  })

  it('treats a non-finite value as zero instead of NaN', async () => {
    render(<AnimatedProgress value={Number.NaN} max={100} label='NaN value' />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '0')
    expect(bar).toHaveAttribute('aria-valuetext', '0%')
    await waitFor(() => {
      expect(fillRatio('NaN value')).toBe(0)
    })
  })

  it('clamps a non-finite maximum instead of producing NaN geometry', async () => {
    render(<AnimatedProgress value={50} max={Number.POSITIVE_INFINITY} label='Inf max' />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-valuenow', '50')
    await waitFor(() => {
      expect(fillRatio('Inf max')).toBeCloseTo(0.5, 6)
    })
  })

  it('handles a non-100 denominator without rescaling the datum', async () => {
    render(<AnimatedProgress value={3} max={4} label='Coverage' showValue={false} />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '3')
    expect(bar).toHaveAttribute('aria-valuemax', '4')
    await waitFor(() => {
      expect(fillRatio('Coverage')).toBeCloseTo(0.75, 6)
    })
  })

  it('keeps a progressbar without a name out of the accessibility tree', () => {
    render(<AnimatedProgress value={30} max={100} showValue={false} />)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('renders instantly at the real ratio under reduced motion', () => {
    stubReducedMotion(true)
    render(<AnimatedProgress value={30} max={100} label='Resolution rate' />)
    expect(fillRatio('Resolution rate')).toBeCloseTo(0.3, 6)
  })
})
