import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

import type { TooltipAnchor } from '../../lib/tooltipPosition.ts'

/**
 * Track which chart element is active and where the tooltip should point.
 *
 * The anchor is stored in container-relative coordinates and only updated when
 * the active element changes (or the pointer moves over the same element).
 * Tooltips do not need per-pixel tracking, so this never re-renders the whole
 * chart on every mouse move more than once per frame — React batches the state
 * update and the chart geometry is memoized separately.
 */
export function useChartTooltip<T extends HTMLElement = HTMLDivElement>() {
  const containerRef = useRef<T | null>(null)
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [anchor, setAnchor] = useState<TooltipAnchor | null>(null)

  const hide = useCallback(() => {
    setActiveKey(null)
    setAnchor(null)
  }, [])

  /** Activate an element and anchor the tooltip at its centre. */
  const showForElement = useCallback((key: string, element: Element | null) => {
    const container = containerRef.current
    if (!container || !element) {
      setActiveKey(key)
      return
    }
    const bounds = container.getBoundingClientRect()
    const rect = element.getBoundingClientRect()
    setActiveKey(key)
    setAnchor({
      x: rect.left - bounds.left + rect.width / 2,
      y: rect.top - bounds.top + rect.height / 2,
    })
  }, [])

  /** Activate an element and anchor the tooltip at the pointer position. */
  const showForPointer = useCallback((key: string, event: ReactPointerEvent) => {
    const container = containerRef.current
    if (!container) {
      setActiveKey(key)
      return
    }
    const bounds = container.getBoundingClientRect()
    setActiveKey(key)
    setAnchor({
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    })
  }, [])

  return { containerRef, activeKey, anchor, hide, showForElement, showForPointer }
}
