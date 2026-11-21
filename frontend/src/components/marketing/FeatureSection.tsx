import { Box, Flex, Grid, Stack, Text } from '@chakra-ui/react'
import {
  ClipboardList,
  Gauge,
  MessageSquare,
  ShieldCheck,
  Ticket,
  UserCog,
  type LucideIcon,
} from 'lucide-react'

import { sectionY } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Reveal } from '../Reveal.tsx'
import { stagger } from '../../theme/motion.ts'
import { Eyebrow, Panel, SectionLead, SectionTitle } from './primitives.tsx'
import { tones } from '../../theme/statusTone.ts'

/* -------------------------------------------------------------------------- */
/* Illustrative mini-visuals                                                  */
/* -------------------------------------------------------------------------- */

const sampleQueue = [
  { ref: 'HD-1042', subject: 'Refund missing from last invoice', status: 'In progress', tone: 'info' as const },
  { ref: 'HD-1039', subject: 'Reset password link has expired', status: 'Open', tone: 'info' as const },
  { ref: 'HD-1031', subject: 'Dashboard slow after CSV export', status: 'Waiting on customer', tone: 'warning' as const },
  { ref: 'HD-1027', subject: 'Add three seats for design team', status: 'Resolved', tone: 'success' as const },
]

function TicketQueueVisual() {
  return (
    <Box mt='6' borderWidth='1px' borderColor={palette.border} borderRadius='l3' overflow='hidden'>
      {sampleQueue.map((row, index) => (
        <Flex
          key={row.ref}
          align='center'
          gap='3'
          px='3.5'
          py='2.5'
          borderBottomWidth={index === sampleQueue.length - 1 ? '0' : '1px'}
          borderColor={palette.borderSubtle}
          bg={index === 0 ? palette.surfaceMuted : 'transparent'}
        >
          <Box boxSize='1.5' borderRadius='full' bg={tones[row.tone].solid} flexShrink={0} aria-hidden />
          <Box minW='0' flex='1'>
            <Text fontSize='xs' color={palette.text} truncate>
              {row.subject}
            </Text>
            <Text fontSize='2xs' color={palette.textFaint} mt='0.5'>
              {row.ref} · {row.status}
            </Text>
          </Box>
        </Flex>
      ))}
    </Box>
  )
}

function AssignmentVisual() {
  return (
    <Flex
      mt='6'
      align='center'
      gap='3'
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      px='3.5'
      py='3'
    >
      <Flex
        boxSize='9'
        align='center'
        justify='center'
        borderRadius='full'
        bg={palette.ink}
        color={palette.textOnInk}
        fontSize='2xs'
        fontWeight='semibold'
        flexShrink={0}
        aria-hidden
      >
        AB
      </Flex>
      <Box minW='0' flex='1'>
        <Text fontSize='2xs' color={palette.textFaint}>
          Assigned to
        </Text>
        <Text fontSize='sm' color={palette.text} truncate>
          Avery Bennett
        </Text>
      </Box>
      <Text
        fontSize='2xs'
        color={palette.textSecondary}
        borderWidth='1px'
        borderColor={palette.border}
        borderRadius='full'
        px='2'
        py='0.5'
        flexShrink={0}
      >
        Agent
      </Text>
    </Flex>
  )
}

function CollaborationVisual() {
  return (
    <Stack gap='2' mt='6'>
      <Box
        borderWidth='1px'
        borderColor={palette.borderSubtle}
        borderRadius='l2'
        bg={palette.surfaceMuted}
        px='3'
        py='2'
      >
        <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
          Internal note · “Customer confirmed the invoice number.”
        </Text>
      </Box>
      <Box borderWidth='1px' borderColor={palette.borderSubtle} borderRadius='l2' px='3' py='2'>
        <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
          Staff message · “Handing this to billing for the credit.”
        </Text>
      </Box>
    </Stack>
  )
}

function AccessVisual() {
  const roles = ['Customer', 'Agent', 'Administrator', 'Owner']
  return (
    <Stack gap='1.5' mt='6'>
      {roles.map((role) => (
        <Flex key={role} align='center' gap='2.5'>
          <ShieldCheck size={13} strokeWidth={1.9} color={palette.textFaint} aria-hidden />
          <Text fontSize='2xs' color={palette.textSecondary}>
            {role}
          </Text>
        </Flex>
      ))}
    </Stack>
  )
}

/* -------------------------------------------------------------------------- */
/* Cards                                                                      */
/* -------------------------------------------------------------------------- */

interface Feature {
  icon: LucideIcon
  title: string
  description: string
}

function FeatureCard({
  icon: Icon,
  title,
  description,
  gridColumn,
  visual,
  delay = 0,
}: Feature & {
  gridColumn?: Record<string, string>
  visual?: React.ReactNode
  delay?: number
}) {
  return (
    <Reveal gridColumn={gridColumn} minW='0' delay={delay} y={16}>
      <Panel
        p={{ base: '5', md: '6' }}
        height='full'
        display='flex'
        flexDirection='column'
        _hover={{ transform: 'translateY(-3px)', boxShadow: palette.shadowMd, borderColor: palette.borderStrong }}
      >
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
          <Icon size={16} strokeWidth={1.9} aria-hidden />
        </Flex>
        <Text mt='4' fontSize='md' fontWeight='medium' color={palette.text} letterSpacing='-0.01em'>
          {title}
        </Text>
        <Text mt='2' fontSize='sm' color={palette.textSecondary} lineHeight='1.65'>
          {description}
        </Text>
        {visual}
      </Panel>
    </Reveal>
  )
}

export function FeatureSection() {
  return (
    <Box as='section' id='features' className='hd-anchor' py={sectionY}>
      <Stack gap='4' maxW='2xl' mb={{ base: '10', md: '14' }}>
        <Reveal y={10} delay={0}>
          <Eyebrow>Features</Eyebrow>
        </Reveal>
        <Reveal y={16} delay={stagger(1)}>
          <SectionTitle>Everything a support team needs, in one place.</SectionTitle>
        </Reveal>
        <Reveal y={14} delay={stagger(2)}>
          <SectionLead>
            HelpDesk keeps customer requests, the people working on them and the conversations
            around them together — without the sprawl of disconnected tools.
          </SectionLead>
        </Reveal>
      </Stack>

      <Grid
        templateColumns={{ base: '1fr', md: 'repeat(2, 1fr)', lg: 'repeat(12, 1fr)' }}
        gap={{ base: '4', md: '5' }}
      >
        <FeatureCard
          delay={0}
          icon={Ticket}
          title='Ticket management'
          description='Organise incoming requests with clear statuses, priorities and categories, and see exactly what still needs attention.'
          gridColumn={{ lg: 'span 7' }}
          visual={<TicketQueueVisual />}
        />
        <FeatureCard
          delay={stagger(1)}
          icon={UserCog}
          title='Intelligent assignment'
          description='Claim work from the queue or hand a ticket to an eligible support agent.'
          gridColumn={{ lg: 'span 5' }}
          visual={<AssignmentVisual />}
        />
        <FeatureCard
          delay={stagger(2)}
          icon={MessageSquare}
          title='Team collaboration'
          description='Internal comments, private staff messages and a complete history on every ticket.'
          gridColumn={{ lg: 'span 3' }}
          visual={<CollaborationVisual />}
        />
        <FeatureCard
          delay={stagger(3)}
          icon={ShieldCheck}
          title='Role-based access'
          description='Customers, agents, administrators and the Owner each see exactly what their role allows.'
          gridColumn={{ lg: 'span 3' }}
          visual={<AccessVisual />}
        />
        <FeatureCard
          delay={stagger(4)}
          icon={ClipboardList}
          title='Customer context'
          description='Ticket details, contact information and attachments in a single, readable view.'
          gridColumn={{ lg: 'span 3' }}
        />
        <FeatureCard
          delay={stagger(5)}
          icon={Gauge}
          title='Operational visibility'
          description='Dashboards and queues that show where the workload sits and what to do next.'
          gridColumn={{ lg: 'span 3' }}
        />
      </Grid>
    </Box>
  )
}
