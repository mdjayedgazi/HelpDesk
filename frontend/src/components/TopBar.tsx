import { Flex, IconButton, Text } from '@chakra-ui/react'
import { PanelLeft } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import { palette } from '../theme/palette.ts'
import { AccountMenu } from './AccountMenu.tsx'
import { Logo } from './Logo.tsx'
import { NotificationsMenu } from './NotificationsMenu.tsx'
import { sectionTitleForPath } from './nav.ts'

export function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const location = useLocation()

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
      bg='rgba(255,255,255,0.85)'
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
        <Flex display={{ base: 'flex', lg: 'none' }}>
          <Logo />
        </Flex>
        <Text
          display={{ base: 'none', lg: 'block' }}
          fontSize='sm'
          fontWeight='medium'
          color={palette.text}
        >
          {sectionTitleForPath(location.pathname)}
        </Text>
      </Flex>
      <Flex align='center' gap='1'>
        <NotificationsMenu />
        <AccountMenu />
      </Flex>
    </Flex>
  )
}
