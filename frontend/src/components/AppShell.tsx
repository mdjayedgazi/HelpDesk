import { Box, Center, Drawer, Flex, Portal, Spinner, Text } from '@chakra-ui/react'
import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import type { User } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { Container } from './Container.tsx'
import { Logo } from './Logo.tsx'
import { navSectionsForRole } from './nav.ts'
import { NewNotificationWatcher } from './NewNotificationWatcher.tsx'
import { SidebarNav } from './Sidebar.tsx'
import { TopBar } from './TopBar.tsx'

export function FullPageLoading() {
  return (
    <Center minHeight='100vh' bg={palette.page}>
      <Spinner size='sm' color={palette.textMuted} />
    </Center>
  )
}

function WorkspaceFooter() {
  return (
    <Flex align='center' gap='2'>
      <Box boxSize='1.5' borderRadius='full' bg={palette.semantic.success} aria-hidden />
      <Box minW='0'>
        <Text as='span' fontSize='2xs' color={palette.textSecondary} display='block'>
          Workspace online
        </Text>
        <Text as='span' fontSize='2xs' color={palette.textFaint} display='block'>
          HelpDesk
        </Text>
      </Box>
    </Flex>
  )
}

export function AppShell({ me }: { me: User }) {
  const sections = navSectionsForRole(me.role)
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  return (
    <Flex minH='100dvh' bg={palette.page}>
      <NewNotificationWatcher key={me.id} />
      <Box
        as='aside'
        display={{ base: 'none', lg: 'block' }}
        position='fixed'
        top='0'
        bottom='0'
        left='0'
        width='64'
        bg={palette.surface}
        borderRightWidth='1px'
        borderColor={palette.border}
        zIndex='10'
      >
        <SidebarNav sections={sections} footer={<WorkspaceFooter />} />
      </Box>

      <Flex direction='column' flex='1' minW='0' ml={{ base: '0', lg: '64' }}>
        <TopBar onOpenNav={() => setNavOpen(true)} role={me.role} />
        <Box as='main' flex='1' minW='0'>
          <Container size='content' py={{ base: '6', md: '8' }}>
            {/* Keyed on the pathname so each workspace view enters with a short
                fade-and-rise. Navigation stays immediate: the route renders on
                the same tick and the animation only decorates the arrival. */}
            <Box key={location.pathname} className='hd-page-enter'>
              <Outlet />
            </Box>
          </Container>
        </Box>
      </Flex>

      <Drawer.Root
        open={navOpen}
        onOpenChange={(details) => setNavOpen(details.open)}
        placement='start'
      >
        <Portal>
          <Drawer.Backdrop bg={palette.overlay} />
          <Drawer.Positioner>
            <Drawer.Content
              bg={palette.surface}
              width='72'
              maxW='80vw'
              borderRightWidth='1px'
              borderColor={palette.border}
            >
              <Drawer.Header srOnly>
                <Drawer.Title>Workspace navigation</Drawer.Title>
              </Drawer.Header>
              <Drawer.Body p='0' display='flex' flexDirection='column' minH='0'>
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
                <Box flex='1' minH='0' overflow='hidden'>
                  <SidebarNav
                    sections={sections}
                    onNavigate={() => setNavOpen(false)}
                    footer={<WorkspaceFooter />}
                  />
                </Box>
              </Drawer.Body>
            </Drawer.Content>
          </Drawer.Positioner>
        </Portal>
      </Drawer.Root>
    </Flex>
  )
}
