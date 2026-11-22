import { Box, Flex, Stack, Text, chakra } from '@chakra-ui/react'
import { NavLink } from 'react-router-dom'

import { palette } from '../theme/palette.ts'
import type { NavSection } from './nav.ts'
import { Logo } from './Logo.tsx'

/**
 * Sidebar navigation.
 *
 * Structure is intentional: sections are labelled, items carry a small icon and
 * the active item is marked by a vertical accent plus an ink-on-surface fill —
 * three independent signals so it survives grayscale and low contrast. Items
 * use a real `NavLink` so the browser exposes the current page correctly.
 *
 * In `compact` mode (the tablet / compact-laptop range) only the icons are
 * shown in a narrow rail, reclaiming horizontal space for the page. Every item
 * keeps its accessible name via `aria-label` and its hover/focus affordance via
 * a native `title`, so nothing is lost for keyboard or touch users. The full
 * labelled sidebar and the mobile drawer both reuse this component, so there is
 * one navigation implementation, not several.
 */
export function SidebarNav({
  sections,
  onNavigate,
  footer,
  compact = false,
}: {
  sections: NavSection[]
  onNavigate?: () => void
  footer?: React.ReactNode
  /** Icon-only rail mode for the 1024–1279 px range. */
  compact?: boolean
}) {
  return (
    <Flex direction='column' height='100%' minH='0'>
      <Flex
        align='center'
        justify={compact ? 'center' : 'flex-start'}
        height='14'
        px={compact ? '0' : '5'}
        borderBottomWidth='1px'
        borderColor={palette.border}
        flexShrink={0}
      >
        <Logo compact={compact} />
      </Flex>

      <Box flex='1' overflowY='auto' py='4' px={compact ? '2' : '3'}>
        <Stack gap={compact ? '2' : '6'}>
          {sections.map((section) => (
            <Stack key={section.label} gap='0.5'>
              {compact ? (
                <Box height='1px' mx='2' my='1' bg={palette.borderSubtle} aria-hidden />
              ) : (
                <Text
                  px='3'
                  pb='1'
                  fontSize='2xs'
                  fontWeight='semibold'
                  letterSpacing='0.08em'
                  textTransform='uppercase'
                  color={palette.textFaint}
                >
                  {section.label}
                </Text>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  style={{ textDecoration: 'none' }}
                  aria-label={compact ? item.label : undefined}
                  title={compact ? item.label : undefined}
                >
                  {({ isActive }) => (
                    <Flex
                      position='relative'
                      align='center'
                      justify={compact ? 'center' : 'flex-start'}
                      gap='2.5'
                      px={compact ? '0' : '3'}
                      py='2'
                      minH={compact ? '10' : undefined}
                      borderRadius='l2'
                      color={isActive ? palette.text : palette.textSecondary}
                      bg={isActive ? palette.surfaceMuted : 'transparent'}
                      fontWeight={isActive ? 'semibold' : 'regular'}
                      transition='background var(--hd-dur-1) var(--hd-ease), color var(--hd-dur-1) var(--hd-ease)'
                      _hover={{ bg: palette.hover, color: palette.text }}
                      _focusVisible={{
                        outline: '2px solid',
                        outlineColor: palette.focus,
                        outlineOffset: '2px',
                      }}
                    >
                      <Box
                        aria-hidden
                        position='absolute'
                        left='0'
                        top='50%'
                        transform='translateY(-50%)'
                        width='2px'
                        height={isActive ? '16px' : '0'}
                        borderRadius='full'
                        bg={palette.accent}
                        transition='height var(--hd-dur-2) var(--hd-ease-out)'
                      />
                      <item.icon
                        size={compact ? 18 : 16}
                        strokeWidth={isActive ? 2.1 : 1.9}
                        aria-hidden
                      />
                      {compact ? (
                        <chakra.span srOnly>{item.label}</chakra.span>
                      ) : (
                        <Text fontSize='sm' truncate>
                          {item.label}
                        </Text>
                      )}
                    </Flex>
                  )}
                </NavLink>
              ))}
            </Stack>
          ))}
        </Stack>
      </Box>

      {footer ? (
        <Box
          px={compact ? '2' : '5'}
          py='4'
          borderTopWidth='1px'
          borderColor={palette.borderSubtle}
          display={compact ? 'flex' : 'block'}
          justifyContent={compact ? 'center' : undefined}
        >
          {compact ? (
            <Box
              boxSize='2'
              borderRadius='full'
              bg={palette.semantic.success}
              aria-label='Workspace online'
              title='Workspace online'
            />
          ) : (
            footer
          )}
        </Box>
      ) : (
        <Box
          px={compact ? '2' : '5'}
          py='4'
          borderTopWidth='1px'
          borderColor={palette.borderSubtle}
        >
          {compact ? (
            <Text fontSize='2xs' color={palette.textFaint} textAlign='center'>
              ·
            </Text>
          ) : (
            <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.02em'>
              HelpDesk · Support workspace
            </Text>
          )}
        </Box>
      )}
    </Flex>
  )
}
