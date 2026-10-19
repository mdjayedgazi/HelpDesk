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
  /** Authenticated app content and marketing body copy grid. */
  content: '1200px',
  /** Wide marketing bands (hero, header, footer) that may breathe a little wider. */
  wide: '1440px',
  /** Single-column reading measure for prose. */
  reading: '720px',
} as const

/** Responsive horizontal padding for a container. */
export const gutter = { base: '5', sm: '6', md: '8', lg: '10' } as const

/** Responsive vertical rhythm between full-width marketing sections. */
export const sectionY = { base: '14', md: '20' } as const

/** Sticky-header height (mirrors `--hd-nav-height`). */
export const navHeight = '16' as const
