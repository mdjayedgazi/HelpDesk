import { IconButton } from '@chakra-ui/react'
import { Moon, Sun } from 'lucide-react'

import { useTheme } from '../theme/colorMode.tsx'
import { palette } from '../theme/palette.ts'

/**
 * Accessible light/dark theme switch.
 *
 * The icon reflects the *action* (the theme you would switch to) and the button
 * reports its state through `aria-pressed`, so the control is never
 * communicated by colour alone.
 */
export function ThemeToggle({ size = 'sm' }: { size?: 'sm' | 'md' }) {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  const label = isDark ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <IconButton
      aria-label={label}
      aria-pressed={isDark}
      title={label}
      variant='ghost'
      size={size}
      color={palette.textSecondary}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l2'
      _hover={{ bg: palette.hover, color: palette.text }}
      onClick={toggle}
    >
      {isDark ? (
        <Sun size={16} strokeWidth={1.9} aria-hidden />
      ) : (
        <Moon size={16} strokeWidth={1.9} aria-hidden />
      )}
    </IconButton>
  )
}
