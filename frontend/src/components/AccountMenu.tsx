import { useClerk, useUser } from '@clerk/react'
import { Box, Button, Menu, Portal, Stack, Text } from '@chakra-ui/react'
import { Bell, ChevronDown, LogOut, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { roleLabels } from '../lib/format.ts'
import { useMe } from '../hooks/useMe.ts'
import { palette } from '../theme/palette.ts'
import { UserAvatar } from './UserAvatar.tsx'

export function AccountMenu() {
  const { signOut } = useClerk()
  const { user } = useUser()
  const { data: me } = useMe()
  const navigate = useNavigate()

  const name =
    me?.full_name || user?.fullName || user?.primaryEmailAddress?.emailAddress || 'Account'
  const email = me?.email || user?.primaryEmailAddress?.emailAddress || ''
  const roleLabel = me ? roleLabels[me.role] : ''

  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <Button
          variant='ghost'
          size='sm'
          px='2'
          height='auto'
          py='1.5'
          gap='2'
          _hover={{ bg: palette.hover }}
          aria-label='Account menu'
        >
          <UserAvatar name={name} src={user?.imageUrl ?? me?.image_url} />
          <Stack align='flex-start' gap='0' display={{ base: 'none', md: 'flex' }}>
            <Text fontSize='sm' fontWeight='medium' lineHeight='1.2' color={palette.text}>
              {name}
            </Text>
            <Text fontSize='xs' color={palette.textMuted} lineHeight='1.2'>
              {roleLabel}
            </Text>
          </Stack>
          <Box color={palette.textMuted} display={{ base: 'none', md: 'block' }}>
            <ChevronDown size={14} aria-hidden />
          </Box>
        </Button>
      </Menu.Trigger>
      <Portal>
        <Menu.Positioner>
          <Menu.Content
            minW='56'
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l2'
            boxShadow={palette.shadowMd}
            py='1.5'
          >
            <Box px='3' py='2'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
                {name}
              </Text>
              {email ? (
                <Text fontSize='xs' color={palette.textMuted} truncate>
                  {email}
                </Text>
              ) : null}
            </Box>
            <Menu.Separator borderColor={palette.borderSubtle} />
            <Menu.Item
              value='profile'
              onSelect={() => navigate('/profile')}
              fontSize='sm'
              _hover={{ bg: palette.hover }}
              gap='2.5'
            >
              <UserRound size={15} aria-hidden />
              <Menu.ItemText>Profile</Menu.ItemText>
            </Menu.Item>
            <Menu.Item
              value='notifications'
              onSelect={() => navigate('/notifications')}
              fontSize='sm'
              _hover={{ bg: palette.hover }}
              gap='2.5'
            >
              <Bell size={15} aria-hidden />
              <Menu.ItemText>Notifications</Menu.ItemText>
            </Menu.Item>
            <Menu.Separator borderColor={palette.borderSubtle} />
            <Menu.Item
              value='signout'
              onSelect={() => {
                void signOut({ redirectUrl: '/' })
              }}
              fontSize='sm'
              _hover={{ bg: palette.hover }}
              gap='2.5'
            >
              <LogOut size={15} aria-hidden />
              <Menu.ItemText>Sign out</Menu.ItemText>
            </Menu.Item>
          </Menu.Content>
        </Menu.Positioner>
      </Portal>
    </Menu.Root>
  )
}
