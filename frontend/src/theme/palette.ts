/**
 * The single source of truth for the monochrome HelpDesk palette.
 *
 * Every surface, border and text tone in the product resolves back to one of
 * these neutrals. Components read from here (or from the matching Chakra
 * semantic tokens defined in `system.ts`) instead of inventing new colors, so
 * the interface stays deliberately black, white and gray.
 */
export const palette = {
  /** Primary page background. */
  page: '#FAFAFA',
  /** Main content surface (cards, panels, sidebar). */
  surface: '#FFFFFF',
  /** Slightly recessed surface for hover and inset areas. */
  surfaceMuted: '#F5F5F5',
  /** Hover surface for interactive rows and menu items. */
  hover: '#F3F3F3',
  /** Stronger inset surface (e.g. code, chips). */
  inset: '#F0F0F0',

  /** Primary text. */
  text: '#111111',
  /** Secondary text. */
  textSecondary: '#525252',
  /** Muted metadata text. */
  textMuted: '#6B6B6B',
  /** Faint text (timestamps, placeholders). */
  textFaint: '#737373',
  /** Text on ink surfaces. */
  textOnInk: '#FFFFFF',

  /** Ink used for primary actions and emphasis. */
  ink: '#111111',
  /** Ink hover. */
  inkHover: '#000000',

  /** Main border. */
  border: '#E5E5E5',
  /** Subtle border. */
  borderSubtle: '#F0F0F0',
  /** Stronger border for emphasis. */
  borderStrong: '#D4D4D4',

  /** Focus ring. */
  focus: '#111111',

  /** Neutral scale used for grayscale pills and depth. */
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
