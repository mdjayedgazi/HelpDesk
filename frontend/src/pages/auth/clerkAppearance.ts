import { palette } from '../../theme/palette.ts'

/**
 * Monochrome skin for the Clerk sign-in / sign-up widgets.
 *
 * Clerk renders its own UI; these overrides keep it consistent with the rest of
 * the product (black primary actions, neutral borders, no brand hue).
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: palette.ink,
    colorText: palette.text,
    colorTextSecondary: palette.textSecondary,
    colorBackground: palette.surface,
    colorInputBackground: palette.surface,
    colorInputText: palette.text,
    colorNeutral: palette.text,
    borderRadius: '6px',
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    fontSize: '0.875rem',
  },
  elements: {
    rootBox: { width: '100%' },
    cardBox: {
      boxShadow: 'none',
      border: `1px solid ${palette.border}`,
      borderRadius: '8px',
      width: '100%',
    },
    card: {
      boxShadow: 'none',
      border: 'none',
      borderRadius: '8px',
      backgroundColor: palette.surface,
    },
    headerTitle: { color: palette.text, fontWeight: '500' },
    headerSubtitle: { color: palette.textSecondary },
    formButtonPrimary: {
      backgroundColor: palette.ink,
      color: palette.textOnInk,
      textTransform: 'none',
      boxShadow: 'none',
      '&:hover': { backgroundColor: palette.inkHover },
    },
    socialButtonsBlockButton: {
      border: `1px solid ${palette.border}`,
      color: palette.text,
      boxShadow: 'none',
    },
    formFieldInput: {
      border: `1px solid ${palette.border}`,
      backgroundColor: palette.surface,
    },
    footerActionLink: { color: palette.text, fontWeight: '500' },
    footer: { backgroundColor: 'transparent' },
  },
} as const
