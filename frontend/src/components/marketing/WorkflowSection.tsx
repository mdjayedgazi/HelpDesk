import { Box, Flex, Grid, Stack, Text } from '@chakra-ui/react'
import { CheckCircle2, Inbox, MessageSquare, UserCog, type LucideIcon } from 'lucide-react'

import { sectionY } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Reveal } from '../Reveal.tsx'
import { Eyebrow, SectionLead, SectionTitle } from './primitives.tsx'

interface Step {
  icon: LucideIcon
  title: string
  description: string
}

const steps: Step[] = [
  {
    icon: Inbox,
    title: 'A request arrives',
    description: 'A customer submits a support request and it lands in the shared queue.',
  },
  {
    icon: UserCog,
    title: 'The team assigns it',
    description: 'An agent claims the ticket or an administrator routes it to the right person.',
  },
  {
    icon: MessageSquare,
    title: 'Everyone stays in the loop',
    description: 'The team replies to the customer and adds internal notes where needed.',
  },
  {
    icon: CheckCircle2,
    title: 'It moves to resolution',
    description: 'The ticket advances through clear statuses until the request is closed.',
  },
]

export function WorkflowSection() {
  return (
    <Box as='section' id='how-it-works' className='hd-anchor' py={sectionY}>
      <Stack gap='4' maxW='2xl' mb={{ base: '10', md: '14' }}>
        <Eyebrow>How it works</Eyebrow>
        <SectionTitle>From first message to resolution.</SectionTitle>
        <SectionLead>
          Four familiar steps, made visible — so customers know what is happening and the team knows
          what to do next.
        </SectionLead>
      </Stack>

      <Grid
        templateColumns={{ base: '1fr', md: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' }}
        gap={{ base: '8', md: '6', lg: '5' }}
      >
        {steps.map((step, index) => (
          <Reveal key={step.title} delay={index * 90} minW='0'>
            <Stack gap='4'>
              <Flex align='center' gap='3'>
                <Flex
                  boxSize='10'
                  align='center'
                  justify='center'
                  borderRadius='full'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  fontSize='sm'
                  fontWeight='semibold'
                  flexShrink={0}
                  aria-hidden
                >
                  {index + 1}
                </Flex>
                {index < steps.length - 1 ? (
                  <Box
                    display={{ base: 'none', lg: 'block' }}
                    flex='1'
                    height='1px'
                    bg={palette.border}
                  />
                ) : null}
              </Flex>

              <Box>
                <Flex align='center' gap='2'>
                  <step.icon size={15} strokeWidth={1.9} color={palette.text} aria-hidden />
                  <Text fontSize='md' fontWeight='medium' color={palette.text} letterSpacing='-0.01em'>
                    {step.title}
                  </Text>
                </Flex>
                <Text mt='2' fontSize='sm' color={palette.textSecondary} lineHeight='1.65'>
                  {step.description}
                </Text>
              </Box>
            </Stack>
          </Reveal>
        ))}
      </Grid>
    </Box>
  )
}
