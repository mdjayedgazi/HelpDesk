import type { TicketPriority, TicketStatus } from '../lib/types.ts'
import { palette } from './palette.ts'

/**
 * The semantic "tone" vocabulary.
 *
 * There are deliberately only five tones. Each one maps to a themed CSS custom
 * property pair (a solid foreground and a soft fill) so badges, dots, charts and
 * legends all speak the same colour language, in both light and dark mode.
 *
 * Colour is never the only carrier of meaning: every tone is rendered alongside
 * an icon and/or a text label.
 */
export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface ToneStyle {
  /** Foreground: text, icon, chart stroke or filled segment. */
  solid: string
  /** Secondary foreground that still meets contrast on `soft`. */
  ink: string
  /** Soft background for badges and chart fills. */
  soft: string
  /** Border for outlined badges. */
  border: string
}

export const tones: Record<Tone, ToneStyle> = {
  neutral: {
    solid: palette.textSecondary,
    ink: palette.text,
    soft: palette.surfaceMuted,
    border: palette.border,
  },
  info: {
    solid: palette.semantic.info,
    ink: palette.semantic.info,
    soft: palette.semantic.infoSoft,
    border: palette.semantic.infoBorder,
  },
  success: {
    solid: palette.semantic.success,
    ink: palette.semantic.success,
    soft: palette.semantic.successSoft,
    border: palette.semantic.successBorder,
  },
  warning: {
    solid: palette.semantic.warning,
    ink: palette.semantic.warning,
    soft: palette.semantic.warningSoft,
    border: palette.semantic.warningBorder,
  },
  danger: {
    solid: palette.semantic.danger,
    ink: palette.semantic.danger,
    soft: palette.semantic.dangerSoft,
    border: palette.semantic.dangerBorder,
  },
}

/**
 * Status → tone.
 *
 * - Open and in-progress are work awaiting the team: informational.
 * - Waiting on customer is blocked by an external party: a warning.
 * - Resolved is healthy: success.
 * - Closed is inactive history: neutral.
 */
export const statusTone: Record<TicketStatus, Tone> = {
  OPEN: 'info',
  IN_PROGRESS: 'info',
  WAITING_ON_CUSTOMER: 'warning',
  RESOLVED: 'success',
  CLOSED: 'neutral',
}

/** Priority → tone. Only high pressure earns a colour. */
export const priorityTone: Record<TicketPriority, Tone> = {
  LOW: 'neutral',
  NORMAL: 'neutral',
  HIGH: 'warning',
  URGENT: 'danger',
}

/** Chart series assignment, ordered so the legend reads naturally. */
export const chartSeries = palette.chart
export const chartSeriesSoft = palette.chartSoft
