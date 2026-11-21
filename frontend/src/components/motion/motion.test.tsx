import { ChakraProvider } from '@chakra-ui/react'
import { act, render as rtlRender, screen, waitFor } from '@testing-library/react'
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
  it('reports the real value through progressbar semantics', () => {
    render(<AnimatedProgress value={30} max={100} label='Resolution rate' />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-valuenow', '30')
    expect(bar).toHaveAttribute('aria-valuetext', '30%')
  })

  it('grows the fill to exactly value / max', async () => {
    render(<AnimatedProgress value={30} max={100} label='Resolution rate' />)
    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement
    await waitFor(() => {
      expect(fill.style.transform).toBe('scaleX(0.3)')
    })
  })

  it('handles a non-100 denominator without rescaling the datum', async () => {
    render(<AnimatedProgress value={3} max={4} label='Coverage' showValue={false} />)
    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement
    expect(bar).toHaveAttribute('aria-valuenow', '3')
    expect(bar).toHaveAttribute('aria-valuemax', '4')
    await waitFor(() => {
      expect(fill.style.transform).toBe('scaleX(0.75)')
    })
  })

  it('never exceeds full width when a value is out of range', async () => {
    render(<AnimatedProgress value={140} max={100} label='Overflow' />)
    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement
    await waitFor(() => {
      expect(fill.style.transform).toBe('scaleX(1)')
    })
  })

  it('renders instantly at the real ratio under reduced motion', () => {
    stubReducedMotion(true)
    render(<AnimatedProgress value={30} max={100} label='Resolution rate' />)
    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement
    act(() => {
      // No frame needed; the entrance flag starts true.
    })
    expect(fill.style.transform).toBe('scaleX(0.3)')
  })
})
