import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

import { usePointerSpotlight } from './usePointerSpotlight.ts'

/** A tiny harness component that attaches the spotlight hook to a div. */
function Host(props: Parameters<typeof usePointerSpotlight>[0]) {
  const ref = usePointerSpotlight<HTMLDivElement>(props)
  return <div ref={ref} data-testid='host' />
}

/**
 * Collect listener registrations that target the spotlight host, ignoring the
 * document/root delegation listeners that React itself installs.
 */
function hostPointerListeners(
  add: { mock: { calls: unknown[][]; instances: unknown[] } },
  host: HTMLElement,
): unknown[][] {
  return add.mock.calls.filter((call, index) => {
    const type = String(call[0])
    return (
      ['pointermove', 'pointerenter', 'pointerleave'].includes(type) &&
      add.mock.instances[index] === host
    )
  })
}

function stubMatchMedia({
  reduce = false,
  fine = true,
  narrow = false,
}: {
  reduce?: boolean
  fine?: boolean
  narrow?: boolean
}) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('prefers-reduced-motion')
        ? reduce
        : query.includes('pointer: fine')
          ? fine
          : query.includes('max-width')
            ? narrow
            : false,
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

/**
 * The spotlight is an enhancement, so the important guarantees are that it
 * stays off where it would be unwelcome and leaves nothing behind on unmount.
 */

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('usePointerSpotlight', () => {
  it('does not attach listeners when reduced motion is requested', () => {
    stubMatchMedia({ reduce: true })
    const add = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    render(<Host />)
    expect(hostPointerListeners(add, screen.getByTestId('host'))).toHaveLength(0)
  })

  it('does not attach listeners on coarse pointers', () => {
    stubMatchMedia({ fine: false })
    const add = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    render(<Host />)
    expect(hostPointerListeners(add, screen.getByTestId('host'))).toHaveLength(0)
  })

  it('does not attach listeners below the minimum viewport width', () => {
    stubMatchMedia({ narrow: true })
    const add = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    render(<Host />)
    expect(hostPointerListeners(add, screen.getByTestId('host'))).toHaveLength(0)
  })

  it('attaches and then fully removes its listeners on unmount', () => {
    stubMatchMedia({})
    const add = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    const remove = vi.spyOn(HTMLElement.prototype, 'removeEventListener')
    const { unmount } = render(<Host />)
    const host = screen.getByTestId('host')

    const added = hostPointerListeners(add, host)
    expect(added.length).toBeGreaterThanOrEqual(3)

    unmount()
    const removedFromHost = remove.mock.calls.filter(
      (_, index) => remove.mock.instances[index] === host,
    )
    for (const type of ['pointermove', 'pointerenter', 'pointerleave']) {
      expect(removedFromHost.some(([removed]) => removed === type)).toBe(true)
    }
  })
})
