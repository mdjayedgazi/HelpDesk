import { useEffect, useRef, useState } from 'react'

/**
 * Measure an element's content width.
 *
 * Charts need a real pixel width so their viewBox can stay 1:1 — scaling an SVG
 * with `preserveAspectRatio='none'` stretches axis labels and looks broken.
 * Returns `null` until the first measurement so callers can render a stable
 * placeholder instead of guessing a width.
 */
export function useElementWidth<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null)
  const [width, setWidth] = useState<number | null>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const measure = () => {
      const next = node.getBoundingClientRect().width
      if (next > 0) setWidth(Math.round(next))
    }

    measure()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }

    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return { ref, width }
}
