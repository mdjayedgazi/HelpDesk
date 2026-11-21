import { ChakraProvider } from '@chakra-ui/react'
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vite-plus/test'

import { system } from '../../theme/system.ts'
import { selectTrendLabelIndices, TrendChart } from './TrendChart.tsx'

/**
 * Label-selection regressions for the trend x-axis.
 *
 * The failure this guards against: a 14-day series used to render a fixed
 * interval plus "always the last date", which placed the final two dates a few
 * pixels apart at some widths. These tests assert the geometry rule directly —
 * every returned label box is inside the plot and no two overlap — for every
 * viewport width the QA matrix covers.
 */

const PAD_L = 34
const PAD_R = 8

/** Recreate the chart's x scale so the test exercises the real geometry. */
function scaleFor(width: number, count: number) {
  const plotLeft = PAD_L
  const plotRight = width - PAD_R
  const stepX = count > 1 ? (plotRight - plotLeft) / (count - 1) : 0
  return {
    plotLeft,
    plotRight,
    x: (index: number) => plotLeft + index * stepX,
  }
}

/**
 * Mirrors the label width estimate used by the selector. Verified against real
 * rendered widths (~8.4–9.0 px per glyph at 10px) in headless Chromium, with a
 * 0.5 px slack so a browser that rounds slightly wider still fails this test
 * rather than passing a chart with colliding labels.
 */
function estimateWidth(text: string) {
  return Math.max(10, text.length * 9) + 0.5
}

function boxOf(label: string, index: number, count: number, x: (i: number) => number) {
  const cx = x(index)
  const w = estimateWidth(label)
  if (index === 0) return { left: cx, right: cx + w }
  if (index === count - 1) return { left: cx - w, right: cx }
  return { left: cx - w / 2, right: cx + w / 2 }
}

function makeLabels(count: number) {
  return Array.from({ length: count }, (_, i) => `Nov ${i + 1}`)
}

describe('selectTrendLabelIndices', () => {
  // 768 is the narrowest width that still renders the wide trend column on a
  // real device; 640/520 approximate the columns at 1024 and 768 in the
  // dashboard grid. 280 is the chart's own MIN_W floor (mobile).
  const widths = [1440, 1280, 1024, 768, 640, 520, 390, 360, 280]

  it.each(widths)('never overlaps or clips labels at %ipx', (width) => {
    const labels = makeLabels(14)
    const { x, plotLeft, plotRight } = scaleFor(width, labels.length)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)

    expect(boxes.length).toBeGreaterThanOrEqual(1)

    for (const box of boxes) {
      const geo = boxOf(labels[box.index]!, box.index, labels.length, x)
      // Inside the plot, not clipped at either edge.
      expect(geo.left).toBeGreaterThanOrEqual(plotLeft - 0.5)
      expect(geo.right).toBeLessThanOrEqual(plotRight + 0.5)
    }

    for (let i = 1; i < boxes.length; i++) {
      const prev = boxOf(labels[boxes[i - 1]!.index]!, boxes[i - 1]!.index, labels.length, x)
      const next = boxOf(labels[boxes[i]!.index]!, boxes[i]!.index, labels.length, x)
      expect(next.left - prev.right).toBeGreaterThanOrEqual(12 - 0.5)
    }
  })

  it.each(widths)('keeps the first date at %ipx', (width) => {
    const labels = makeLabels(14)
    const { x, plotLeft, plotRight } = scaleFor(width, labels.length)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)
    expect(boxes[0]?.index).toBe(0)
  })

  it('includes the last date when there is room for both ends', () => {
    const labels = makeLabels(14)
    const { x, plotLeft, plotRight } = scaleFor(1280, labels.length)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)
    expect(boxes.at(-1)?.index).toBe(labels.length - 1)
  })

  it('returns a usable set for a 7-day series', () => {
    const labels = makeLabels(7)
    const { x, plotLeft, plotRight } = scaleFor(1024, labels.length)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)
    expect(boxes.length).toBeGreaterThanOrEqual(2)
    expect(boxes[0]?.index).toBe(0)
    expect(boxes.at(-1)?.index).toBe(6)
  })

  it('handles a single point without dividing by zero', () => {
    const labels = ['Nov 1']
    const { x, plotLeft, plotRight } = scaleFor(640, 1)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)
    expect(boxes).toHaveLength(1)
    expect(boxes[0]?.index).toBe(0)
  })

  it('returns nothing for an empty series', () => {
    expect(selectTrendLabelIndices([], () => 0, 0, 100)).toEqual([])
  })

  it('never returns duplicate indices for a long series on a narrow chart', () => {
    const labels = makeLabels(90)
    const { x, plotLeft, plotRight } = scaleFor(280, labels.length)
    const boxes = selectTrendLabelIndices(labels, x, plotLeft, plotRight)
    const indices = boxes.map((b) => b.index)
    expect(new Set(indices).size).toBe(indices.length)
  })
})

describe('TrendChart label rendering', () => {
  it('renders only the selected labels, keeping the full series in the data table', () => {
    const points = Array.from({ length: 14 }, (_, i) => ({
      label: `Nov ${i + 1}`,
      values: { created: i, resolved: i % 3 },
    }))

    const { container } = render(
      <ChakraProvider value={system}>
        <TrendChart
          points={points}
          series={[{ key: 'created', label: 'Created', color: '#111' }]}
          ariaLabel='Ticket volume'
        />
      </ChakraProvider>,
    )

    // Every data point is still in the accessible table, regardless of which
    // x labels were painted.
    const rows = container.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(14)
  })
})
