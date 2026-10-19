import { Box, Button, Flex, Grid, Heading, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import {
  ArrowUp,
  CheckCircle2,
  CircleDot,
  History,
  MessageSquare,
  ShieldCheck,
  Ticket,
  UserRound,
  Users,
} from 'lucide-react'
import { useRef, useState, type KeyboardEvent } from 'react'

import { sectionY } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Container } from '../Container.tsx'
import { Eyebrow, Panel, SectionLead, SectionTitle } from './primitives.tsx'

/* -------------------------------------------------------------------------- */
/* Illustrative visuals                                                       */
/* -------------------------------------------------------------------------- */

const board = [
  {
    title: 'Open',
    cards: [
      { ref: 'HD-1039', subject: 'Reset password link expired', tone: 'High' },
      { ref: 'HD-1036', subject: 'Cannot connect the mobile app', tone: 'Normal' },
    ],
  },
  {
    title: 'In progress',
    cards: [{ ref: 'HD-1042', subject: 'Refund missing from invoice', tone: 'High' }],
  },
  { title: 'Resolved', cards: [{ ref: 'HD-1027', subject: 'Add three seats', tone: 'Low' }] },
]

function TicketsVisual() {
  return (
    <SimpleGrid columns={{ base: 1, sm: 3 }} gap='3'>
      {board.map((column) => (
        <Box
          key={column.title}
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l3'
          bg={palette.surfaceMuted}
          p='3'
        >
          <Flex align='center' justify='space-between' mb='3'>
            <Text fontSize='2xs' fontWeight='semibold' color={palette.textSecondary} letterSpacing='0.04em'>
              {column.title.toUpperCase()}
            </Text>
            <Text fontSize='2xs' color={palette.textFaint}>
              {column.cards.length}
            </Text>
          </Flex>
          <Stack gap='2'>
            {column.cards.map((card) => (
              <Box
                key={card.ref}
                bg={palette.surface}
                borderWidth='1px'
                borderColor={palette.border}
                borderRadius='l2'
                p='2.5'
                boxShadow={palette.shadowSm}
              >
                <Text fontSize='2xs' color={palette.textFaint}>
                  {card.ref}
                </Text>
                <Text fontSize='xs' color={palette.text} mt='1' lineHeight='1.4'>
                  {card.subject}
                </Text>
                <Flex align='center' gap='1.5' mt='2' color={palette.textMuted} fontSize='2xs'>
                  <ArrowUp size={11} strokeWidth={2.2} aria-hidden />
                  {card.tone} priority
                </Flex>
              </Box>
            ))}
          </Stack>
        </Box>
      ))}
    </SimpleGrid>
  )
}

function CollaborationVisual() {
  return (
    <Stack gap='3'>
      <Flex align='center' gap='2.5' px='3' py='2.5' borderWidth='1px' borderColor={palette.border} borderRadius='l3'>
        <Flex
          boxSize='8'
          align='center'
          justify='center'
          borderRadius='full'
          bg={palette.ink}
          color={palette.textOnInk}
          flexShrink={0}
          aria-hidden
        >
          <UserRound size={14} strokeWidth={1.9} />
        </Flex>
        <Box minW='0'>
          <Text fontSize='2xs' color={palette.textFaint}>
            Customer reply
          </Text>
          <Text fontSize='xs' color={palette.text} truncate>
            “That did the trick, thank you.”
          </Text>
        </Box>
      </Flex>

      <Flex align='center' gap='2.5' px='3' py='2.5' borderWidth='1px' borderColor={palette.border} borderRadius='l3' bg={palette.surfaceMuted}>
        <Flex
          boxSize='8'
          align='center'
          justify='center'
          borderRadius='full'
          borderWidth='1px'
          borderColor={palette.borderStrong}
          color={palette.textSecondary}
          flexShrink={0}
          aria-hidden
        >
          <MessageSquare size={14} strokeWidth={1.9} />
        </Flex>
        <Box minW='0'>
          <Text fontSize='2xs' color={palette.textFaint}>
            Internal note · staff only
          </Text>
          <Text fontSize='xs' color={palette.text} truncate>
            “Locking the ticket and adding the number to the report.”
          </Text>
        </Box>
      </Flex>

      <Flex align='center' gap='2.5' px='3' py='2.5' borderWidth='1px' borderColor={palette.borderSubtle} borderRadius='l3'>
        <History size={14} strokeWidth={1.9} color={palette.textFaint} aria-hidden />
        <Text fontSize='2xs' color={palette.textMuted}>
          Full history retained on every change
        </Text>
      </Flex>
    </Stack>
  )
}

const roleAccess = [
  { role: 'Customer', icon: UserRound, points: ['Raise and follow their own tickets', 'Reply within their support thread'] },
  { role: 'Agent', icon: Ticket, points: ['Work the shared ticket queue', 'Comment internally and reply to customers'] },
  { role: 'Administrator', icon: Users, points: ['Manage tickets and user accounts', 'Review account requests'] },
  { role: 'Owner', icon: ShieldCheck, points: ['Full administrative access', 'Broadcast internal messages to staff'] },
]

function AccessVisual() {
  return (
    <SimpleGrid columns={{ base: 1, sm: 2 }} gap='3'>
      {roleAccess.map((entry) => (
        <Box
          key={entry.role}
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l3'
          p='3.5'
          bg={palette.surface}
        >
          <Flex align='center' gap='2' mb='2.5'>
            <entry.icon size={14} strokeWidth={1.9} color={palette.text} aria-hidden />
            <Text fontSize='xs' fontWeight='medium' color={palette.text}>
              {entry.role}
            </Text>
          </Flex>
          <Stack gap='1.5'>
            {entry.points.map((point) => (
              <Flex key={point} align='flex-start' gap='2'>
                <CheckCircle2 size={12} strokeWidth={2} color={palette.textFaint} aria-hidden />
                <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
                  {point}
                </Text>
              </Flex>
            ))}
          </Stack>
        </Box>
      ))}
    </SimpleGrid>
  )
}

/* -------------------------------------------------------------------------- */
/* Tabs                                                                       */
/* -------------------------------------------------------------------------- */

interface ShowcaseItem {
  id: string
  label: string
  icon: typeof Ticket
  title: string
  description: string
  points: string[]
  visual: React.ReactNode
}

const SHOWCASE: ShowcaseItem[] = [
  {
    id: 'tickets',
    label: 'Tickets',
    icon: CircleDot,
    title: 'A single queue for every request',
    description:
      'Requests move through clear statuses — open, in progress, waiting on the customer, resolved — so nobody has to guess what happens next.',
    points: ['Statuses, priorities and categories', 'Claim or assign the next piece of work', 'Searchable, filterable ticket lists'],
    visual: <TicketsVisual />,
  },
  {
    id: 'collaboration',
    label: 'Collaboration',
    icon: MessageSquare,
    title: 'Talk to customers, and to each other',
    description:
      'Keep the customer conversation public and the working notes private. Comment threads, staff messages and ticket history stay on the ticket.',
    points: ['Internal comments, invisible to customers', 'Private staff messaging with the Owner', 'A retained history of every change'],
    visual: <CollaborationVisual />,
  },
  {
    id: 'access',
    label: 'Access control',
    icon: ShieldCheck,
    title: 'The right view for every role',
    description:
      'HelpDesk separates customer-facing support from internal staff operations and Owner-level management, so each person sees only what their role allows.',
    points: ['Customer, agent, administrator and Owner roles', 'Permissions enforced by the backend', 'Internal messaging stays internal'],
    visual: <AccessVisual />,
  },
]

export function ShowcaseSection() {
  const [index, setIndex] = useState(0)
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const active = SHOWCASE[index]

  const focusTab = (next: number) => {
    const target = (next + SHOWCASE.length) % SHOWCASE.length
    setIndex(target)
    tabRefs.current[target]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault()
        focusTab(index + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault()
        focusTab(index - 1)
        break
      case 'Home':
        event.preventDefault()
        focusTab(0)
        break
      case 'End':
        event.preventDefault()
        focusTab(SHOWCASE.length - 1)
        break
      default:
        break
    }
  }

  return (
    <Box
      as='section'
      id='product'
      className='hd-anchor'
      py={sectionY}
      bg={palette.surfaceMuted}
      borderTopWidth='1px'
      borderBottomWidth='1px'
      borderColor={palette.border}
    >
      <Container size='wide'>
        <Stack gap='4' maxW='2xl' mb={{ base: '8', md: '10' }}>
          <Eyebrow>Product tour</Eyebrow>
          <SectionTitle>See how a request moves through HelpDesk.</SectionTitle>
          <SectionLead>
            Pick an area to explore. The illustrations are examples built into this page — nothing
            here requires an account.
          </SectionLead>
        </Stack>

        <Box
          role='tablist'
          aria-label='Product areas'
          display='flex'
          gap='1'
          p='1'
          bg={palette.surface}
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l3'
          width={{ base: 'full', md: 'fit-content' }}
          boxShadow={palette.shadowSm}
          onKeyDown={onKeyDown}
        >
          {SHOWCASE.map((item, itemIndex) => {
            const selected = itemIndex === index
            return (
              <Button
                key={item.id}
                ref={(node) => {
                  tabRefs.current[itemIndex] = node
                }}
                id={`showcase-tab-${item.id}`}
                role='tab'
                aria-selected={selected}
                aria-controls={`showcase-panel-${item.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setIndex(itemIndex)}
                variant='ghost'
                size='sm'
                flex={{ base: '1', md: 'none' }}
                height='9'
                px='3.5'
                bg={selected ? palette.surfaceMuted : 'transparent'}
                color={selected ? palette.text : palette.textSecondary}
                borderWidth='1px'
                borderColor={selected ? palette.border : 'transparent'}
                borderRadius='l2'
                fontWeight={selected ? 'medium' : 'regular'}
                _hover={{ bg: selected ? palette.surfaceMuted : palette.hover, color: palette.text }}
              >
                <item.icon size={15} strokeWidth={1.9} aria-hidden />
                {item.label}
              </Button>
            )
          })}
        </Box>

        <Box
          key={active.id}
          role='tabpanel'
          id={`showcase-panel-${active.id}`}
          aria-labelledby={`showcase-tab-${active.id}`}
          tabIndex={0}
          className='hd-fade-up'
          mt={{ base: '6', md: '8' }}
        >
          <Grid templateColumns={{ base: '1fr', lg: 'minmax(0, 0.85fr) minmax(0, 1.15fr)' }} gap={{ base: '8', lg: '12' }} alignItems='center'>
            <Stack gap='4'>
              <Heading as='h3' fontSize={{ base: 'xl', md: '2xl' }} fontWeight='semibold' letterSpacing='-0.02em' color={palette.text}>
                {active.title}
              </Heading>
              <Text fontSize='sm' color={palette.textSecondary} lineHeight='1.7'>
                {active.description}
              </Text>
              <Stack gap='2.5' pt='1'>
                {active.points.map((point) => (
                  <Flex key={point} align='flex-start' gap='2.5'>
                    <Box mt='0.5' color={palette.textFaint} flexShrink={0}>
                      <CheckCircle2 size={14} strokeWidth={2} aria-hidden />
                    </Box>
                    <Text fontSize='sm' color={palette.textSecondary}>
                      {point}
                    </Text>
                  </Flex>
                ))}
              </Stack>
            </Stack>

            <Panel p={{ base: '4', md: '5' }} bg={palette.surface}>
              {active.visual}
            </Panel>
          </Grid>
        </Box>
      </Container>
    </Box>
  )
}
