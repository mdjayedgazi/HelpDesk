/**
 * The single source of truth for the monochrome HelpDesk palette.
 *
 * Every value points at a CSS custom property declared in
 * `src/theme/tokens.css`, which flips between its light and dark value when the
 * `dark` class is present on `<html>`. Components therefore keep reading plain
 * names (`palette.surface`) while the rendered colour follows the active theme
 * automatically — no component needs to know which theme is active.
 *
 * The `gray` scale is intentionally *static*: it is a neutral ramp shared by
 * both themes and is only used to seed Chakra's own colour tokens.
 */
export const palette = {
  /** Primary page background. */
  page: 'var(--hd-page)',
  /** Main content surface (cards, panels, sidebar). */
  surface: 'var(--hd-surface)',
  /** Slightly recessed surface for hover and inset areas. */
  surfaceMuted: 'var(--hd-surface-muted)',
  /** Raised surface that reads as elevated above the page. */
  elevated: 'var(--hd-elevated)',
  /** Hover surface for interactive rows and menu items. */
  hover: 'var(--hd-hover)',
  /** Stronger inset surface (e.g. code, chips). */
  inset: 'var(--hd-inset)',

  /** Primary text. */
  text: 'var(--hd-text)',
  /** Secondary text. */
  textSecondary: 'var(--hd-text-secondary)',
  /** Muted metadata text. */
  textMuted: 'var(--hd-text-muted)',
  /** Faint text (timestamps, placeholders). */
  textFaint: 'var(--hd-text-faint)',
  /** Text on ink surfaces. */
  textOnInk: 'var(--hd-text-on-ink)',

  /** Ink used for primary actions and emphasis. */
  ink: 'var(--hd-ink)',
    logo: 'rgba(11,11,13,0.74)',
  /** Ink hover. */
  inkHover: 'var(--hd-ink-hover)',

  /** Main border. */
  border: 'var(--hd-border)',
  /** Subtle border. */
  borderSubtle: 'var(--hd-border-subtle)',
  /** Stronger border for emphasis. */
  borderStrong: 'var(--hd-border-strong)',

  /** Focus ring. */
  focus: 'var(--hd-focus)',

  /** Translucent overlay for dialogs, drawers and lightboxes. */
  overlay: 'var(--hd-overlay)',
  /** Translucent chrome for sticky headers. */
  glass: 'var(--hd-glass)',
  /** Fine grid/texture stroke. */
  grid: 'var(--hd-grid)',

  /** Elevation presets. */
  shadowSm: 'var(--hd-shadow-sm)',
  shadowMd: 'var(--hd-shadow-md)',
  shadowLg: 'var(--hd-shadow-lg)',
  shadowXl: 'var(--hd-shadow-xl)',
  shadowPanel: 'var(--hd-shadow-panel)',

  /**
   * Static neutral ramp. Deliberately identical in both themes so Chakra's own
   * semantic tokens (which pair `gray.50` with `gray.950`, etc.) keep working.
   */
  gray: {
    50: '#FAFAFA',
    100: '#F5F5F5',
    200: '#E5E5E5',
    300: '#D4D4D4',
    400: '#A3A3A3',
    500: '#888888',
    600: '#666666',
    700: '#404040',
    800: '#262626',
    900: '#171717',
    950: '#0A0A0A',
  },
} as const

export type Palette = typeof palette
