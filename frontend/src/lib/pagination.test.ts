import { describe, expect, it } from 'vite-plus/test'

import {
  canPaginate,
  clampPage,
  nextPage,
  pageRange,
  pageWindow,
  previousPage,
} from './pagination.ts'

/**
 * The navigation contract the bug report asks for, pinned as pure arithmetic.
 *
 * The critical properties: a page never exceeds `totalPages`, Next wraps from
 * the last page to 1, Previous wraps from 1 to the last page, and the window
 * only ever contains real page numbers.
 */

describe('nextPage', () => {
  it.each([
    [1, 15, 2],
    [5, 15, 6],
    [10, 15, 11],
    [14, 15, 15],
    // Wrap: last page -> first.
    [15, 15, 1],
  ])('page %i of %i -> %i', (page, total, expected) => {
    expect(nextPage(page, total)).toBe(expected)
  })

  it('never moves when there is a single page', () => {
    expect(nextPage(1, 1)).toBe(1)
    expect(nextPage(1, 0)).toBe(1)
  })
})

describe('previousPage', () => {
  it.each([
    [15, 15, 14],
    [2, 15, 1],
    // Wrap: first page -> last.
    [1, 15, 15],
  ])('page %i of %i -> %i', (page, total, expected) => {
    expect(previousPage(page, total)).toBe(expected)
  })

  it('never moves when there is a single page', () => {
    expect(previousPage(1, 1)).toBe(1)
    expect(previousPage(1, 0)).toBe(1)
  })
})

describe('clampPage', () => {
  it.each([
    [0, 15, 1],
    [-4, 15, 1],
    [99, 15, 15],
    [7, 15, 7],
    [3.9, 15, 3],
  ])('page %i of %i clamps to %i', (page, total, expected) => {
    expect(clampPage(page, total)).toBe(expected)
  })

  it('treats a zero/NaN total as a single page', () => {
    expect(clampPage(5, 0)).toBe(1)
    expect(clampPage(Number.NaN, 10)).toBe(1)
  })
})

describe('canPaginate', () => {
  it('is false for zero or one page', () => {
    expect(canPaginate(0)).toBe(false)
    expect(canPaginate(1)).toBe(false)
  })
  it('is true for two or more pages', () => {
    expect(canPaginate(2)).toBe(true)
  })
})

describe('pageWindow', () => {
  it('lists every page when the set is small', () => {
    expect(pageWindow(2, 5)).toEqual([1, 2, 3, 4, 5])
  })

  it('always includes the first and last page', () => {
    const items = pageWindow(10, 20)
    expect(items[0]).toBe(1)
    expect(items.at(-1)).toBe(20)
  })

  it('never includes an out-of-range page number', () => {
    for (const current of [1, 2, 10, 19, 20]) {
      const items = pageWindow(current, 20)
      for (const item of items) {
        if (item === 'ellipsis') continue
        expect(item).toBeGreaterThanOrEqual(1)
        expect(item).toBeLessThanOrEqual(20)
      }
    }
  })

  it('keeps the current page inside the window', () => {
    const items = pageWindow(10, 20)
    expect(items).toContain(10)
  })

  it('uses ellipses only for genuine gaps', () => {
    const items = pageWindow(10, 20)
    // No two adjacent ellipses, and never an ellipsis at either end.
    expect(items[0]).not.toBe('ellipsis')
    expect(items.at(-1)).not.toBe('ellipsis')
    for (let i = 1; i < items.length; i += 1) {
      expect(items[i] === 'ellipsis' && items[i - 1] === 'ellipsis').toBe(false)
    }
  })
})

describe('pageRange', () => {
  it('reports a full first page', () => {
    expect(pageRange(1, 20, 300)).toEqual({ start: 1, end: 20 })
  })

  it('reports a partial final page', () => {
    expect(pageRange(15, 20, 282)).toEqual({ start: 281, end: 282 })
  })

  it('reports zero for an empty set', () => {
    expect(pageRange(1, 20, 0)).toEqual({ start: 0, end: 0 })
  })
})
