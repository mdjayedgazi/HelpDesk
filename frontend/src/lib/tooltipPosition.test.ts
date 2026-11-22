import { describe, expect, it } from 'vite-plus/test'

import {
  TOOLTIP_OFFSET,
  TOOLTIP_PADDING,
  placeTooltip,
} from './tooltipPosition.ts'

/**
 * Tooltip placement is pure geometry, so these tests pin the rules that keep a
 * panel on screen: prefer the right, flip left at the edge, and clamp inside
 * the container on both axes.
 */

const base = {
  containerWidth: 800,
  containerHeight: 400,
  tooltipWidth: 200,
  tooltipHeight: 90,
}

describe('placeTooltip', () => {
  it('prefers the right side with a consistent gap', () => {
    const placement = placeTooltip({ x: 200, y: 200 }, base)
    expect(placement.side).toBe('right')
    expect(placement.left).toBe(200 + TOOLTIP_OFFSET)
    // Centred vertically on the anchor.
    expect(placement.top).toBe(200 - 45)
    expect(placement.flippedY).toBe(false)
  })

  it('flips to the left when the right edge would overflow', () => {
    const placement = placeTooltip({ x: 700, y: 200 }, base)
    expect(placement.side).toBe('left')
    expect(placement.left).toBe(700 - TOOLTIP_OFFSET - 200)
  })

  it('keeps a minimum padding from the left edge when flipped', () => {
    const placement = placeTooltip({ x: 20, y: 200 }, {
      ...base,
      tooltipWidth: 800,
    })
    // Right side cannot fit an 800px tooltip beside x=20, so it flips; the
    // clamp then holds it at the padding rather than a negative left.
    expect(placement.side).toBe('left')
    expect(placement.left).toBe(TOOLTIP_PADDING)
  })

  it('clamps the top edge so a high anchor does not clip', () => {
    const placement = placeTooltip({ x: 200, y: 4 }, base)
    expect(placement.top).toBe(TOOLTIP_PADDING)
    expect(placement.flippedY).toBe(true)
  })

  it('clamps the bottom edge so a low anchor does not clip', () => {
    const placement = placeTooltip({ x: 200, y: 398 }, base)
    expect(placement.top).toBe(base.containerHeight - base.tooltipHeight - TOOLTIP_PADDING)
    expect(placement.flippedY).toBe(true)
  })

  it('never returns a negative offset when the tooltip is wider than the box', () => {
    const placement = placeTooltip({ x: 10, y: 10 }, {
      containerWidth: 120,
      containerHeight: 120,
      tooltipWidth: 300,
      tooltipHeight: 200,
    })
    expect(placement.left).toBe(TOOLTIP_PADDING)
    expect(placement.top).toBe(TOOLTIP_PADDING)
  })
})
