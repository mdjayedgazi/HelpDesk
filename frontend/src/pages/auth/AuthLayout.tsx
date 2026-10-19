import { Box, Flex, Heading, Stack, Text } from '@chakra-ui/react'

import { Logo } from '../../components/Logo.tsx'
import { palette } from '../../theme/palette.ts'

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <Flex minHeight='100vh' bg={palette.page} direction='column'>
      <Flex
        align='center'
        justify='space-between'
        px={{ base: '5', md: '10' }}
        height='16'
        borderBottomWidth='1px'
        borderColor={palette.border}
        bg={palette.surface}
      >
        <Logo />
        <Text fontSize='xs' color={palette.textMuted} display={{ base: 'none', sm: 'block' }}>
          Support, organised.
        </Text>
      </Flex>
      <Flex
        flex='1'
        align='center'
        justify='center'
        px={{ base: '4', md: '6' }}
        py={{ base: '10', md: '16' }}
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
