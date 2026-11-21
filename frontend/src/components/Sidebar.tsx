import { Box, Flex, Stack, Text } from '@chakra-ui/react'
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
 */
export function SidebarNav({
  sections,
  onNavigate,
  footer,
}: {
  sections: NavSection[]
  onNavigate?: () => void
  footer?: React.ReactNode
}) {
  return (
    <Flex direction='column' height='100%' minH='0'>
      <Flex
        align='center'
        height='14'
        px='5'
        borderBottomWidth='1px'
        borderColor={palette.border}
        flexShrink={0}
      >
        <Logo />
      </Flex>

      <Box flex='1' overflowY='auto' py='4' px='3'>
        <Stack gap='6'>
          {sections.map((section) => (
            <Stack key={section.label} gap='0.5'>
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
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  style={{ textDecoration: 'none' }}
                >
                  {({ isActive }) => (
                    <Flex
                      position='relative'
                      align='center'
                      gap='2.5'
                      px='3'
                      py='2'
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
                        size={16}
                        strokeWidth={isActive ? 2.1 : 1.9}
                        aria-hidden
                      />
                      <Text fontSize='sm' truncate>
                        {item.label}
                      </Text>
                    </Flex>
                  )}
                </NavLink>
              ))}
            </Stack>
          ))}
        </Stack>
      </Box>

      {footer ? (
        <Box px='5' py='4' borderTopWidth='1px' borderColor={palette.borderSubtle}>
          {footer}
        </Box>
      ) : (
        <Box px='5' py='4' borderTopWidth='1px' borderColor={palette.borderSubtle}>
          <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.02em'>
            HelpDesk · Support workspace
          </Text>
        </Box>
      )}
    </Flex>
  )
}
