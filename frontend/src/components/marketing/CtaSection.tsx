import { Box, Button, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import { useAuth } from '@clerk/react'
import { ArrowRight } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'

import { sectionY } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Panel } from './primitives.tsx'

export function CtaSection() {
  const { isLoaded, isSignedIn } = useAuth()
  const signedIn = isLoaded && isSignedIn

  return (
    <Box as='section' pt={sectionY} pb={sectionY}>
      <Panel
        position='relative'
        overflow='hidden'
        borderRadius='l5'
        boxShadow={palette.shadowLg}
        p={{ base: '8', md: '14' }}
      >
        <Box position='absolute' inset='0' className='hd-grid-bg' opacity={0.5} aria-hidden />

        <Stack position='relative' gap='5' align='center' textAlign='center' maxW='xl' mx='auto'>
          <Heading
            as='h2'
            fontSize={{ base: '2xl', md: '4xl' }}
            fontWeight='semibold'
            letterSpacing='-0.03em'
            lineHeight='1.12'
            color={palette.text}
            textWrap='balance'
          >
            Make every support conversation count.
          </Heading>
          <Text fontSize={{ base: 'sm', md: 'md' }} color={palette.textSecondary} lineHeight='1.7'>
            Keep requests, replies and internal notes together — so nothing is lost between a
            customer's first message and a resolved ticket.
          </Text>

          <Flex gap='3' wrap='wrap' justify='center' pt='1'>
            {signedIn ? (
              <Button
                asChild
                bg={palette.ink}
                color={palette.textOnInk}
                height='11'
                px='5'
                _hover={{ bg: palette.inkHover }}
              >
                <RouterLink to='/dashboard'>
                  Open workspace
                  <ArrowRight size={16} aria-hidden />
                </RouterLink>
              </Button>
            ) : (
              <>
                <Button
                  asChild
                  bg={palette.ink}
                  color={palette.textOnInk}
                  height='11'
                  px='5'
                  _hover={{ bg: palette.inkHover }}
                >
                  <RouterLink to='/sign-up'>
                    Get started
                    <ArrowRight size={16} aria-hidden />
                  </RouterLink>
                </Button>
                <Button
                  asChild
                  variant='outline'
                  borderColor={palette.border}
                  color={palette.text}
                  bg={palette.surface}
                  height='11'
                  px='5'
                  _hover={{ bg: palette.hover, borderColor: palette.borderStrong }}
                >
                  <RouterLink to='/sign-in'>Sign in</RouterLink>
                </Button>
              </>
            )}
          </Flex>
        </Stack>
      </Panel>
    </Box>
  )
}
