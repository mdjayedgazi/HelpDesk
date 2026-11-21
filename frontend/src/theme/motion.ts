/**
 * The single motion vocabulary for HelpDesk.
 *
 * Every entrance, reveal, counter and chart reveal reads its timing from here
 * so the product feels like one interface instead of a collection of
 * independently animated widgets. Values mirror the `--hd-dur-*` custom
 * properties in `tokens.css`; keeping the JS numbers and the CSS variables in
 * sync is deliberate — CSS transitions are used wherever possible, and the JS
 * side only needs durations for count-up and one-shot entrance flags.
 */

export const duration = {
  /** Hover / press feedback. */
  fast: 140,
  /** Small state changes (menus, row selection). */
  base: 200,
  /** Component transitions. */
  slow: 320,
  /** Section and panel entrances. */
  reveal: 420,
  /** Hero and heading choreography. */
  entrance: 560,
  /** KPI count-up. */
  count: 800,
  /** Progressive chart draw. */
  chart: 900,
  /** Ambient float cycle (milliseconds). */
  ambient: 7500,
} as const

export const easing = {
  /** General purpose; gentle start, decisive finish. */
  standard: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
  /** Decelerate: entrances settling into place. */
  out: 'cubic-bezier(0.16, 1, 0.3, 1)',
  /** Both ends smoothed: ambient loops. */
  inOut: 'cubic-bezier(0.45, 0, 0.55, 1)',
} as const

/** Step between siblings in a staggered reveal, in milliseconds. */
export const staggerStep = 70

/**
 * Delay for the nth sibling in a stagger, clamped so a long list cannot push
 * its last item seconds into the future. Callers keep the sibling count small.
 */
export function stagger(index: number, max = 8): number {
  return Math.min(Math.max(index, 0), max) * staggerStep
}

/** Ambient float parameters. Small, slow, and varied per instance. */
export const float = {
  minDistance: 4,
  maxDistance: 8,
  minDuration: 6000,
  maxDuration: 9000,
} as const

/**
 * True when the operating system asks for reduced motion.
 *
 * Returns `true` when `matchMedia` is unavailable (tests, SSR, old browsers) so
 * every consumer takes the safe path: render the final state immediately.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Re-exported so callers can build transition strings without hardcoding. */
export const motionVars = {
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
} as const

/** Standard transition helpers used across cards, rows and panels. */
export const transitions = {
  /** Colour/border only; never moves layout. */
  colors: `background ${motionVars.base} ${motionVars.ease}, border-color ${motionVars.base} ${motionVars.ease}, color ${motionVars.base} ${motionVars.ease}`,
  /** Colour plus a tiny lift for interactive cards. */
  lift: `transform ${motionVars.base} ${motionVars.easeOut}, box-shadow ${motionVars.base} ${motionVars.easeOut}, border-color ${motionVars.base} ${motionVars.ease}, background ${motionVars.base} ${motionVars.ease}`,
} as const
