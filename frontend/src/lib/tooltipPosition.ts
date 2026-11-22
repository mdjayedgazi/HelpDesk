/**
 * Placement math for chart tooltips.
 *
 * Tooltips live inside the chart's own relatively-positioned wrapper, so the
 * browser never clips them behind a neighbouring card and there is no portal
 * to keep in sync with scroll. This module has no DOM dependency, which keeps
 * the clamping rules unit-testable without a browser.
 */

export interface TooltipBounds {
  /** Width of the container the tooltip is positioned within, in px. */
  containerWidth: number
  /** Height of the container, in px. */
  containerHeight: number
  /** Rendered tooltip width, in px. */
  tooltipWidth: number
  /** Rendered tooltip height, in px. */
  tooltipHeight: number
}

export interface TooltipAnchor {
  /** Horizontal anchor inside the container, in px. */
  x: number
  /** Vertical anchor inside the container, in px. */
  y: number
}

export interface TooltipPlacement {
  /** Final left offset inside the container, in px. */
  left: number
  /** Final top offset inside the container, in px. */
  top: number
  /** Which side of the anchor the tooltip was placed on. */
  side: 'right' | 'left'
  /** Whether the tooltip had to flip above the anchor. */
  flippedY: boolean
}

/** Gap between the anchor and the tooltip edge, in px. */
export const TOOLTIP_OFFSET = 12
/** Minimum distance kept from any container edge, in px. */
export const TOOLTIP_PADDING = 4

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

/**
 * Place a tooltip beside an anchor, preferring the right side and flipping to
 * the left when the right edge would overflow. Vertical placement is centred on
 * the anchor and clamped inside the container, so a tooltip near the top or
 * bottom edge stays fully visible. All coordinates are relative to the
 * container's top-left corner.
 */
export function placeTooltip(anchor: TooltipAnchor, bounds: TooltipBounds): TooltipPlacement {
  const {
    containerWidth,
    containerHeight,
    tooltipWidth,
    tooltipHeight,
  } = bounds

  const maxLeft = Math.max(TOOLTIP_PADDING, containerWidth - tooltipWidth - TOOLTIP_PADDING)
  const maxTop = Math.max(TOOLTIP_PADDING, containerHeight - tooltipHeight - TOOLTIP_PADDING)

  const preferRight = anchor.x + TOOLTIP_OFFSET + tooltipWidth <= containerWidth - TOOLTIP_PADDING
  const side: TooltipPlacement['side'] = preferRight ? 'right' : 'left'

  const rawLeft =
    side === 'right'
      ? anchor.x + TOOLTIP_OFFSET
      : anchor.x - TOOLTIP_OFFSET - tooltipWidth
  const left = clamp(rawLeft, TOOLTIP_PADDING, maxLeft)

  const centeredTop = anchor.y - tooltipHeight / 2
  const top = clamp(centeredTop, TOOLTIP_PADDING, maxTop)
  const flippedY = centeredTop < TOOLTIP_PADDING || centeredTop > maxTop

  return { left, top, side, flippedY }
}
