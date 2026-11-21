import { createSystem, defaultConfig, defineConfig, type SystemStyleObject } from '@chakra-ui/react'

import { palette } from './palette.ts'

const fontStack =
  'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

const monoStack =
  'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

/**
 * HelpDesk design system.
 *
 * Built on Chakra's default system but re-tuned to a strict monochrome palette:
 * neutral gray tokens replace the default hue scale so the product keeps its
 * black / white / grey identity. Semantic colour is deliberately *not* a full
 * rainbow — only four meaning-bearing families exist (info, success, warning,
 * danger) and they are used for status, priority and data visualisation. They
 * resolve to the themed custom properties in `tokens.css`, so a component can
 * read `fg.error` or `palette.semantic.danger` and get a value that flips with
 * the active theme.
 *
 * Theme-able values resolve to CSS custom properties declared in
 * `tokens.css` (via `palette`). Because those properties change under
 * `html.dark`, every semantic token — and every component that reads them —
 * follows the active light/dark theme without any per-component branching.
 */
const config = defineConfig({
  cssVarsPrefix: 'hd',
  globalCss: {
    'html, body': {
      bg: palette.page,
      color: palette.text,
    },
    html: {
      textSizeAdjust: '100%',
      scrollBehavior: 'smooth',
      // Paint the base surface from one place so the marketing chrome and the
      // authenticated shell never disagree about the page background.
      backgroundColor: palette.page,
    },
    body: {
      fontFamily: 'body',
      fontSize: 'sm',
      lineHeight: '1.55',
      fontSynthesis: 'none',
      textRendering: 'optimizeLegibility',
    },
    '*, *::before, *::after': {
      borderColor: palette.border,
    },
    '*::selection': {
      bg: palette.ink,
      color: palette.textOnInk,
    },
    '*:focus-visible': {
      outline: '2px solid',
      outlineColor: palette.focus,
      outlineOffset: '2px',
      borderRadius: 'xs',
    },
    a: {
      color: 'inherit',
    },
    img: {
      maxWidth: '100%',
    },
    '@media (prefers-reduced-motion: reduce)': {
      '*, *::before, *::after': {
        animationDuration: '0.001ms !important',
        animationIterationCount: '1 !important',
        transitionDuration: '0.001ms !important',
        scrollBehavior: 'auto !important',
      },
    } as SystemStyleObject,
  },
  theme: {
    tokens: {
      fonts: {
        heading: { value: fontStack },
        body: { value: fontStack },
        mono: { value: monoStack },
      },
      colors: {
        gray: {
          50: { value: palette.gray[50] },
          100: { value: palette.gray[100] },
          200: { value: palette.gray[200] },
          300: { value: palette.gray[300] },
          400: { value: palette.gray[400] },
          500: { value: palette.gray[500] },
          600: { value: palette.gray[600] },
          700: { value: palette.gray[700] },
          800: { value: palette.gray[800] },
          900: { value: palette.gray[900] },
          950: { value: palette.gray[950] },
        },
      },
      radii: {
        l1: { value: '4px' },
        l2: { value: '6px' },
        l3: { value: '8px' },
        l4: { value: '12px' },
        l5: { value: '16px' },
      },
    },
    semanticTokens: {
      colors: {
        bg: {
          DEFAULT: { value: palette.page },
          subtle: { value: palette.surfaceMuted },
          muted: { value: palette.inset },
          emphasized: { value: palette.border },
          inverted: { value: palette.ink },
          panel: { value: palette.surface },
          error: { value: palette.semantic.dangerSoft },
          warning: { value: palette.semantic.warningSoft },
          success: { value: palette.semantic.successSoft },
          info: { value: palette.semantic.infoSoft },
        },
        fg: {
          DEFAULT: { value: palette.text },
          muted: { value: palette.textSecondary },
          subtle: { value: palette.textMuted },
          inverted: { value: palette.textOnInk },
          error: { value: palette.semantic.danger },
          warning: { value: palette.semantic.warning },
          success: { value: palette.semantic.success },
          info: { value: palette.semantic.info },
        },
        border: {
          DEFAULT: { value: palette.border },
          muted: { value: palette.borderSubtle },
          subtle: { value: palette.borderSubtle },
          emphasized: { value: palette.borderStrong },
          inverted: { value: palette.ink },
          error: { value: palette.semantic.dangerBorder },
          warning: { value: palette.semantic.warningBorder },
          success: { value: palette.semantic.successBorder },
          info: { value: palette.semantic.infoBorder },
        },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
