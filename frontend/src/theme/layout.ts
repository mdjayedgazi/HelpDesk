/**
 * Layout tokens shared by the public marketing pages and the authenticated
 * application shell.
 *
 * Everything that controls spacing, width or rhythm lives here so the two
 * surfaces stay aligned to the same system instead of drifting into their own
 * arbitrary paddings.
 */

/** Container widths. */
export const widths = {
  /**
   * Authenticated workspace content.
   *
   * This is deliberately wider than the marketing measure: after the fixed
   * 256 px sidebar and page padding are subtracted, a 1200 px cap left roughly
   * 230 px of dead space on each side at 1920 px. The workspace cap only takes
   * effect on very wide displays; below it the container fills the available
   * main column exactly.
   */
  workspace: '1680px',
  /** Marketing body copy grid. */
  content: '1200px',
  /** Wide marketing bands (hero, header, footer) that may breathe a little wider. */
  wide: '1440px',
  /** Single-column reading measure for prose. */
  reading: '720px',
  /** Form/detail column that should not stretch edge to edge on wide screens. */
  detail: '1120px',
} as const

/** Responsive horizontal padding for a container. */
export const gutter = { base: '5', sm: '6', md: '8', lg: '10' } as const

/**
 * Horizontal padding for the authenticated workspace.
 *
 * Slightly tighter on phones so tables and charts keep usable room, and a
 * little more generous only on very wide displays where the extra gutter costs
 * nothing.
 */
export const workspaceGutter = {
  base: '4',
  sm: '6',
  md: '8',
  lg: '10',
  '2xl': '12',
} as const

/** Responsive vertical rhythm between full-width marketing sections. */
export const sectionY = { base: '14', md: '20' } as const

/** Sticky-header height (mirrors `--hd-nav-height`). */
export const navHeight = '16' as const
