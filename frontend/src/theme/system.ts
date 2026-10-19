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
 * neutral gray tokens replace the default hue scale and every semantic color
 * (including error/success/warning/info) collapses to grayscale so that no
 * component can accidentally introduce a rainbow accent.
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
      },
    },
    semanticTokens: {
      colors: {
        bg: {
          DEFAULT: { value: { _light: palette.page } },
          subtle: { value: { _light: palette.surfaceMuted } },
          muted: { value: { _light: palette.inset } },
          emphasized: { value: { _light: palette.border } },
          inverted: { value: { _light: palette.ink } },
          panel: { value: { _light: palette.surface } },
          error: { value: { _light: palette.inset } },
          warning: { value: { _light: palette.inset } },
          success: { value: { _light: palette.inset } },
          info: { value: { _light: palette.inset } },
        },
        fg: {
          DEFAULT: { value: { _light: palette.text } },
          muted: { value: { _light: palette.textSecondary } },
          subtle: { value: { _light: palette.textMuted } },
          inverted: { value: { _light: palette.textOnInk } },
          error: { value: { _light: palette.text } },
          warning: { value: { _light: palette.text } },
          success: { value: { _light: palette.text } },
          info: { value: { _light: palette.text } },
        },
        border: {
          DEFAULT: { value: { _light: palette.border } },
          muted: { value: { _light: palette.borderSubtle } },
          subtle: { value: { _light: palette.borderSubtle } },
          emphasized: { value: { _light: palette.borderStrong } },
          inverted: { value: { _light: palette.ink } },
          error: { value: { _light: palette.border } },
          warning: { value: { _light: palette.border } },
          success: { value: { _light: palette.border } },
          info: { value: { _light: palette.border } },
        },
      },
    },
  },
})

export const system = createSystem(defaultConfig, config)
