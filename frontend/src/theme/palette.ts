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
  /** Logo plate tone (themed, unlike the old hard-coded value). */
  logo: 'var(--hd-logo-plate)',
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

  /**
   * Controlled cobalt accent.
   *
   * The one non-semantic colour in the product. It marks selected/active
   * interaction (current nav item, chosen tab, non-semantic progress) and is
   * never used to decorate a surface. It is a shade darker than the brief's
   * `#5278C7` so small text keeps >= 4.5:1 contrast on white.
   */
  accent: 'var(--hd-accent)',
  accentSoft: 'var(--hd-accent-soft)',
  accentBorder: 'var(--hd-accent-border)',
  accentContrast: 'var(--hd-accent-contrast)',

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
   * Semantic colour.
   *
   * Colour carries meaning in this product: it marks a status family, a
   * priority pressure or a data series — never decoration. Every family ships
   * a solid foreground plus a soft tint for badges and chart fills, and is
   * always paired with an icon or a text label so colour is never the only
   * signal. See `--hd-info` … `--hd-danger` in `tokens.css`.
   */
  semantic: {
    info: 'var(--hd-info)',
    infoSoft: 'var(--hd-info-soft)',
    infoBorder: 'var(--hd-info-border)',
    success: 'var(--hd-success)',
    successSoft: 'var(--hd-success-soft)',
    successBorder: 'var(--hd-success-border)',
    warning: 'var(--hd-warning)',
    warningSoft: 'var(--hd-warning-soft)',
    warningBorder: 'var(--hd-warning-border)',
    danger: 'var(--hd-danger)',
    dangerSoft: 'var(--hd-danger-soft)',
    dangerBorder: 'var(--hd-danger-border)',
  },

  /** Chart series colours, in legend order. */
  chart: [
    'var(--hd-chart-1)',
    'var(--hd-chart-2)',
    'var(--hd-chart-3)',
    'var(--hd-chart-4)',
    'var(--hd-chart-5)',
  ],
  chartSoft: [
    'var(--hd-chart-1-soft)',
    'var(--hd-chart-2-soft)',
    'var(--hd-chart-3-soft)',
    'var(--hd-chart-4-soft)',
    'var(--hd-chart-5-soft)',
  ],
  chartGrid: 'var(--hd-chart-grid)',
  chartAxis: 'var(--hd-chart-axis)',

  /** Motion tokens shared by CSS and inline transitions. */
  motion: {
    ease: 'var(--hd-ease)',
    easeOut: 'var(--hd-ease-out)',
    easeInOut: 'var(--hd-ease-in-out)',
    fast: 'var(--hd-dur-1)',
    base: 'var(--hd-dur-2)',
    slow: 'var(--hd-dur-3)',
    reveal: 'var(--hd-dur-4)',
    entrance: 'var(--hd-dur-5)',
    count: 'var(--hd-dur-6)',
    chart: 'var(--hd-dur-chart)',
  },

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
