import { Box, Flex, Heading, Link, Stack, Text } from '@chakra-ui/react'
import { Link as RouterLink } from 'react-router-dom'

import { Container } from '../../components/Container.tsx'
import { Logo } from '../../components/Logo.tsx'
import { ThemeToggle } from '../../components/ThemeToggle.tsx'
import { navHeight } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <Flex minHeight='100dvh' bg={palette.page} direction='column'>
      <Box borderBottomWidth='1px' borderColor={palette.border} bg={palette.surface}>
        <Container size='wide'>
          <Flex align='center' justify='space-between' gap='4' height={navHeight}>
            <Link asChild _hover={{ textDecoration: 'none' }} aria-label='HelpDesk home'>
              <RouterLink to='/'>
                <Logo />
              </RouterLink>
            </Link>
            <Flex align='center' gap='3'>
              <Text fontSize='xs' color={palette.textMuted} display={{ base: 'none', sm: 'block' }}>
                Support, organised.
              </Text>
              <ThemeToggle />
            </Flex>
          </Flex>
        </Container>
      </Box>

      <Flex
        flex='1'
        align='center'
        justify='center'
        px={{ base: '5', md: '6' }}
        py={{ base: '12', md: '16' }}
      >
        <Stack gap='8' width='full' maxW='md' align='center'>
          <Stack gap='2' textAlign='center' maxW='sm'>
            <Heading
              fontSize='2xl'
              fontWeight='medium'
              letterSpacing='-0.02em'
              color={palette.text}
            >
              Welcome to HelpDesk
            </Heading>
            <Text fontSize='sm' color={palette.textSecondary}>
              Sign in to submit requests, track progress and talk to support.
            </Text>
          </Stack>
          <Box
            as='section'
            display='flex'
            justifyContent='center'
            width='full'
            aria-label='Authentication'
          >
            {children}
          </Box>
        </Stack>
      </Flex>
    </Flex>
  )
}
