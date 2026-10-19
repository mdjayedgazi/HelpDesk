import { Box, Flex, Grid, Stack, Text } from '@chakra-ui/react'
import { Headset, ShieldCheck, Users, type LucideIcon } from 'lucide-react'

import { sectionY } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Reveal } from '../Reveal.tsx'
import { Eyebrow, Panel, SectionLead, SectionTitle } from './primitives.tsx'

interface Layer {
  icon: LucideIcon
  label: string
  description: string
}

const layers: Layer[] = [
  {
    icon: Headset,
    label: 'Customer support',
    description: 'Customers raise and follow their own requests, and talk to the team about them.',
  },
  {
    icon: Users,
    label: 'Internal staff operations',
    description: 'Agents and administrators share the ticket queue, comments and staff messaging.',
  },
  {
    icon: ShieldCheck,
    label: 'Owner-level management',
    description: 'The Owner holds full administrative access, including internal broadcasts to staff.',
  },
]

export function SecuritySection() {
  return (
    <Box
      as='section'
      id='security'
      className='hd-anchor'
      py={sectionY}
      borderTopWidth='1px'
      borderColor={palette.border}
    >
      <Grid templateColumns={{ base: '1fr', lg: 'minmax(0, 0.9fr) minmax(0, 1.1fr)' }} gap={{ base: '10', lg: '16' }} alignItems='center'>
        <Reveal>
          <Stack gap='4' maxW='xl'>
            <Eyebrow>Security &amp; access control</Eyebrow>
            <SectionTitle>Separated by design, not by convention.</SectionTitle>
            <SectionLead>
              HelpDesk keeps customer-facing support workflows apart from internal staff operations
              and Owner-level management. Every request is authorised against the signed-in user's
              role, so signing in does not by itself grant access to someone else's work.
            </SectionLead>
            <Text fontSize='sm' color={palette.textMuted} lineHeight='1.7'>
              Internal notes and staff messages stay within the staff workspace. Customers only ever
              see their own support conversations.
            </Text>
          </Stack>
        </Reveal>

        <Reveal delay={120}>
          <Stack gap='3'>
            {layers.map((layer, index) => (
              <Panel key={layer.label} p={{ base: '4', md: '5' }}>
                <Flex align='center' gap='3.5'>
                  <Flex
                    boxSize='9'
                    align='center'
                    justify='center'
                    borderRadius='l2'
                    borderWidth='1px'
                    borderColor={palette.border}
                    bg={palette.surfaceMuted}
                    color={palette.text}
                    flexShrink={0}
                  >
                    <layer.icon size={16} strokeWidth={1.9} aria-hidden />
                  </Flex>
                  <Box minW='0'>
                    <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                      {layer.label}
                    </Text>
                    <Text mt='1' fontSize='sm' color={palette.textSecondary} lineHeight='1.6'>
                      {layer.description}
                    </Text>
                  </Box>
                  <Text
                    ms='auto'
                    fontSize='2xs'
                    color={palette.textFaint}
                    letterSpacing='0.04em'
                    flexShrink={0}
                    display={{ base: 'none', sm: 'block' }}
                  >
                    {String(index + 1).padStart(2, '0')}
                  </Text>
                </Flex>
              </Panel>
            ))}
          </Stack>
        </Reveal>
      </Grid>
    </Box>
  )
}
