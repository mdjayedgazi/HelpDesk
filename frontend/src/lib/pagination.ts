/**
 * Pagination arithmetic, kept pure so the rules are unit-testable without a
 * browser or a server.
 *
 * The backend is the source of truth for `total_pages`; these helpers only
 * decide what the controls may do *given* a valid page count. They never
 * manufacture a page beyond `totalPages`.
 */

export type PageItem = number | 'ellipsis'

/** Clamp a requested page into `[1, totalPages]`. */
export function clampPage(page: number, totalPages: number): number {
  const safeTotal = Math.max(1, Math.floor(totalPages) || 1)
  if (!Number.isFinite(page)) return 1
  return Math.min(Math.max(Math.trunc(page), 1), safeTotal)
}

/**
 * Circular "next": the page after `page`, wrapping from the last page to 1.
 * A single-page (or empty) result never moves; there is nowhere to go.
 */
export function nextPage(page: number, totalPages: number): number {
  const total = Math.max(1, Math.floor(totalPages) || 1)
  if (total <= 1) return 1
  const current = clampPage(page, total)
  return current >= total ? 1 : current + 1
}

/**
 * Circular "previous": the page before `page`, wrapping from page 1 to the
 * last page. A single-page result never moves.
 */
export function previousPage(page: number, totalPages: number): number {
  const total = Math.max(1, Math.floor(totalPages) || 1)
  if (total <= 1) return 1
  const current = clampPage(page, total)
  return current <= 1 ? total : current - 1
}

/** Whether the Prev/Next controls should be interactive at all. */
export function canPaginate(totalPages: number): boolean {
  return Math.max(1, Math.floor(totalPages) || 1) > 1
}

/**
 * The page numbers to render, with `'ellipsis'` markers between gaps.
 *
 * Only real page numbers in `[1, totalPages]` are ever returned, so the control
 * can never offer a nonexistent page. The first and last page are always shown;
 * a moving window of at most `maxSlots` total entries surrounds the current
 * page. Very small result sets render every page without ellipses.
 */
export function pageWindow(
  current: number,
  totalPages: number,
  maxSlots = 7,
): PageItem[] {
  const total = Math.max(1, Math.floor(totalPages) || 1)
  if (total <= maxSlots) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const page = clampPage(current, total)
  // First and last are reserved; the rest form the window.
  const windowSize = Math.max(1, maxSlots - 2)
  let start = Math.max(2, page - Math.floor((windowSize - 1) / 2))
  let end = start + windowSize - 1
  if (end > total - 1) {
    end = total - 1
    start = Math.max(2, end - windowSize + 1)
  }

  const items: PageItem[] = [1]
  if (start > 2) items.push('ellipsis')
  for (let candidate = start; candidate <= end; candidate += 1) {
    items.push(candidate)
  }
  if (end < total - 1) items.push('ellipsis')
  items.push(total)
  return items
}

/** Inclusive "showing X–Y" bounds for the current page. */
export function pageRange(
  page: number,
  pageSize: number,
  total: number,
): { start: number; end: number } {
  if (total <= 0) return { start: 0, end: 0 }
  const safePageSize = Math.max(1, Math.floor(pageSize) || 1)
  const start = (clampPage(page, Math.ceil(total / safePageSize)) - 1) * safePageSize + 1
  const end = Math.min(total, start + safePageSize - 1)
  return { start, end }
}
