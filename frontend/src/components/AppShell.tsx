import { Box, Center, Drawer, Flex, Portal, Spinner } from '@chakra-ui/react'
import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import type { User } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { navSectionsForRole } from './nav.ts'
import { SidebarNav } from './Sidebar.tsx'
import { TopBar } from './TopBar.tsx'

export function FullPageLoading() {
  return (
    <Center minHeight='100vh' bg={palette.page}>
      <Spinner size='sm' color={palette.textMuted} />
    </Center>
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
    <Flex className='min-h-screen' bg={palette.page}>
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
        <SidebarNav sections={sections} />
      </Box>

      <Flex direction='column' flex='1' minW='0' ml={{ base: '0', lg: '64' }}>
        <TopBar onOpenNav={() => setNavOpen(true)} />
        <Box as='main' flex='1' minW='0'>
          <Box className='mx-auto w-full max-w-[1200px] px-4 py-6 md:px-8 md:py-8'>
            <Outlet />
          </Box>
        </Box>
      </Flex>

      <Drawer.Root
        open={navOpen}
        onOpenChange={(details) => setNavOpen(details.open)}
        placement='start'
      >
        <Portal>
          <Drawer.Backdrop bg='rgba(17,17,17,0.32)' />
          <Drawer.Positioner>
            <Drawer.Content
              bg={palette.surface}
              width='72'
              maxW='80vw'
              borderRightWidth='1px'
              borderColor={palette.border}
            >
              <SidebarNav sections={sections} onNavigate={() => setNavOpen(false)} />
            </Drawer.Content>
          </Drawer.Positioner>
        </Portal>
      </Drawer.Root>
    </Flex>
  )
}
