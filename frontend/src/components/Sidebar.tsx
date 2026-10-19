import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { NavLink } from 'react-router-dom'

import { palette } from '../theme/palette.ts'
import type { NavSection } from './nav.ts'
import { Logo } from './Logo.tsx'

export function SidebarNav({
  sections,
  onNavigate,
}: {
  sections: NavSection[]
  onNavigate?: () => void
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
            <Stack key={section.label} gap='1'>
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
                      align='center'
                      gap='3'
                      px='3'
                      py='2'
                      borderRadius='l2'
                      color={isActive ? palette.text : palette.textSecondary}
                      bg={isActive ? palette.hover : 'transparent'}
                      fontWeight={isActive ? 'medium' : 'regular'}
                      transition='background 0.16s ease, color 0.16s ease'
                      _hover={{ bg: palette.hover, color: palette.text }}
                    >
                      <item.icon size={16} strokeWidth={1.9} aria-hidden />
                      <Text fontSize='sm'>{item.label}</Text>
                    </Flex>
                  )}
                </NavLink>
              ))}
            </Stack>
          ))}
        </Stack>
      </Box>

      <Box px='5' py='4' borderTopWidth='1px' borderColor={palette.borderSubtle}>
        <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.02em'>
          HelpDesk · Support workspace
        </Text>
      </Box>
    </Flex>
  )
}
