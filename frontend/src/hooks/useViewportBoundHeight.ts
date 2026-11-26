import { useLayoutEffect, useRef, useState } from 'react'

/**
 * Bounds an element to the height actually available below it in the viewport.
 *
 * The messaging panes sit under a variable amount of chrome (the sticky top
 * bar, the page header and — for the Owner inbox — the tab/action strip), so a
 * single hardcoded `calc(100dvh - Npx)` cannot fit every page. Measuring the
 * element's own top edge gives the exact remaining height, letting the
 * conversation list and message thread scroll internally while the composer
 * stays pinned to the bottom instead of the whole document scrolling.
 *
 * Returns `undefined` below `minWidth`, where the layout stacks vertically and
 * should grow with its content instead. `measureKey` re-runs the measurement
 * when the pane is only rendered after its data loads.
 */
export function useViewportBoundHeight<T extends HTMLElement>(
  enabled = true,
  {
    bottomGutter = 32,
    minWidth = 1024,
    measureKey,
  }: { bottomGutter?: number; minWidth?: number; measureKey?: unknown } = {},
) {
  const ref = useRef<T>(null)
  const [height, setHeight] = useState<number | undefined>(undefined)

  useLayoutEffect(() => {
    if (!enabled) return

    const compute = () => {
      const node = ref.current
      if (!node || window.innerWidth < minWidth) {
        setHeight((current) => (current === undefined ? current : undefined))
        return
      }
      const top = node.getBoundingClientRect().top
      const available = Math.floor(window.innerHeight - top - bottomGutter)
      const next = available > 0 ? available : undefined
      // Commit only real changes so the ResizeObserver cannot loop on its own
      // resize.
      setHeight((current) => (current === next ? current : next))
    }

    compute()
    window.addEventListener('resize', compute)
    // Re-measure when the page above the pane grows or shrinks (e.g. the
    // "From the Owner" panel finishing its fetch).
    const observer = new ResizeObserver(compute)
    observer.observe(document.documentElement)
    if (ref.current) observer.observe(ref.current)
    return () => {
      window.removeEventListener('resize', compute)
      observer.disconnect()
    }
  }, [enabled, bottomGutter, minWidth, measureKey])

  return { ref, height }
}
