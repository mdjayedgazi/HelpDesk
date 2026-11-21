import { Box, Flex, IconButton, Text } from '@chakra-ui/react'
import { PanelLeft } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import type { Role } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { AccountMenu } from './AccountMenu.tsx'
import { Logo } from './Logo.tsx'
import { NotificationsMenu } from './NotificationsMenu.tsx'
import { ThemeToggle } from './ThemeToggle.tsx'
import { navSectionForPath, sectionTitleForPath } from './nav.ts'

/**
 * Sticky application top bar.
 *
 * It answers "where am I?" with a two-part label — the nav *section* in muted
 * type and the page title in ink — so the title is never ambiguous between
 * areas that share a word (Tickets vs Account requests). The rest of the bar is
 * utility: theme, notifications and the account menu.
 */
export function TopBar({ onOpenNav, role }: { onOpenNav: () => void; role?: Role }) {
  const location = useLocation()
  const title = sectionTitleForPath(location.pathname)
  const section = role ? navSectionForPath(role, location.pathname) : null

  return (
    <Flex
      as='header'
      position='sticky'
      top='0'
      zIndex='20'
      align='center'
      justify='space-between'
      gap='3'
      height='14'
      px={{ base: '3', md: '6' }}
      bg={palette.glass}
      backdropFilter='blur(8px)'
      borderBottomWidth='1px'
      borderColor={palette.border}
      flexShrink={0}
    >
      <Flex align='center' gap='3' minW='0'>
        <IconButton
          aria-label='Open navigation'
          variant='ghost'
          size='sm'
          display={{ base: 'inline-flex', lg: 'none' }}
          color={palette.textSecondary}
          _hover={{ bg: palette.hover, color: palette.text }}
          onClick={onOpenNav}
        >
          <PanelLeft size={18} strokeWidth={1.9} aria-hidden />
        </IconButton>
        <Flex display={{ base: 'flex', lg: 'none' }} flexShrink={0}>
          <Logo compact />
        </Flex>
        <Flex
          display={{ base: 'none', lg: 'flex' }}
          align='baseline'
          gap='2'
          minW='0'
        >
          {section ? (
            <Text fontSize='xs' color={palette.textFaint} flexShrink={0}>
              {section}
            </Text>
          ) : null}
          {section ? (
            <Box width='1px' height='3' bg={palette.border} flexShrink={0} aria-hidden />
          ) : null}
          <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
            {title}
          </Text>
        </Flex>
        <Text
          display={{ base: 'block', lg: 'none' }}
          fontSize='sm'
          fontWeight='medium'
          color={palette.text}
          truncate
        >
          {title}
        </Text>
      </Flex>
      <Flex align='center' gap='1' flexShrink={0}>
        <ThemeToggle />
        <NotificationsMenu />
        <AccountMenu />
      </Flex>
    </Flex>
  )
}
