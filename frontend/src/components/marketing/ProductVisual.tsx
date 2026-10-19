import { Box, Flex, Text } from '@chakra-ui/react'
import {
  ArrowUp,
  Clock,
  LayoutList,
  MessageSquare,
  Paperclip,
  Settings2,
  ShieldCheck,
  Sparkles,
  Ticket,
  UserRound,
} from 'lucide-react'

import { palette } from '../../theme/palette.ts'
import { StatusDot } from './primitives.tsx'

/**
 * Illustrative product visual for the hero.
 *
 * Built entirely from real components and icons — no screenshot, and no call to
 * a protected API. The example tickets are clearly fictional sample data that
 * lives only in this file.
 */

interface QueueRow {
  ref: string
  subject: string
  status: string
  filled: boolean
  active?: boolean
}

const queue: QueueRow[] = [
  {
    ref: 'HD-1042',
    subject: 'Refund missing from last invoice',
    status: 'In progress',
    filled: true,
    active: true,
  },
  { ref: 'HD-1039', subject: 'Reset password link has expired', status: 'Open', filled: true },
  { ref: 'HD-1031', subject: 'Dashboard slow after CSV export', status: 'Waiting on customer', filled: false },
  { ref: 'HD-1027', subject: 'Add three seats for design team', status: 'Resolved', filled: false },
]

function WindowChrome() {
  return (
    <Flex
      align='center'
      gap='3'
      px='4'
      height='11'
      borderBottomWidth='1px'
      borderColor={palette.border}
      bg={palette.surfaceMuted}
    >
      <Flex gap='1.5' aria-hidden>
        <Box boxSize='2.5' borderRadius='full' bg={palette.borderStrong} />
        <Box boxSize='2.5' borderRadius='full' bg={palette.borderStrong} />
        <Box boxSize='2.5' borderRadius='full' bg={palette.border} />
      </Flex>
      <Flex align='center' gap='2' color={palette.textMuted} fontSize='2xs' minW='0'>
        <Sparkles size={12} strokeWidth={1.9} aria-hidden />
        <Text truncate letterSpacing='0.02em'>
          HelpDesk · Support workspace
        </Text>
      </Flex>
    </Flex>
  )
}

function Rail() {
  return (
    <Flex
      display={{ base: 'none', md: 'flex' }}
      direction='column'
      align='center'
      gap='2'
      py='4'
      px='2'
      width='12'
      borderRightWidth='1px'
      borderColor={palette.borderSubtle}
      bg={palette.surfaceMuted}
      flexShrink={0}
    >
      {[LayoutList, Ticket, MessageSquare, UserRound, Settings2].map((Icon, index) => (
        <Flex
          key={index}
          boxSize='7'
          align='center'
          justify='center'
          borderRadius='l2'
          bg={index === 1 ? palette.ink : 'transparent'}
          color={index === 1 ? palette.textOnInk : palette.textFaint}
          aria-hidden
        >
          <Icon size={14} strokeWidth={1.9} />
        </Flex>
      ))}
    </Flex>
  )
}

function Queue() {
  return (
    <Flex direction='column' flex='1' minW='0'>
      <Flex
        align='center'
        justify='space-between'
        gap='2'
        px='4'
        py='3'
        borderBottomWidth='1px'
        borderColor={palette.borderSubtle}
      >
        <Text fontSize='xs' fontWeight='semibold' color={palette.text} letterSpacing='-0.01em'>
          Ticket queue
        </Text>
        <Flex
          align='center'
          gap='1'
          px='2'
          py='0.5'
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='full'
          fontSize='2xs'
          color={palette.textMuted}
        >
          <Clock size={11} strokeWidth={2} aria-hidden />
          4 open
        </Flex>
      </Flex>

      <Box flex='1' minW='0'>
        {queue.map((row) => (
          <Flex
            key={row.ref}
            align='center'
            gap='3'
            px='4'
            py='2.5'
            borderBottomWidth='1px'
            borderColor={palette.borderSubtle}
            bg={row.active ? palette.hover : 'transparent'}
          >
            <StatusDot filled={row.filled} />
            <Box minW='0' flex='1'>
              <Text
                fontSize='xs'
                fontWeight={row.active ? 'medium' : 'regular'}
                color={palette.text}
                truncate
              >
                {row.subject}
              </Text>
              <Text fontSize='2xs' color={palette.textFaint} mt='0.5'>
                {row.ref} · {row.status}
              </Text>
            </Box>
            {row.filled ? (
              <Flex
                boxSize='5'
                align='center'
                justify='center'
                borderRadius='full'
                borderWidth='1px'
                borderColor={palette.border}
                color={palette.textMuted}
                aria-hidden
              >
                <ArrowUp size={11} strokeWidth={2.2} />
              </Flex>
            ) : null}
          </Flex>
        ))}
      </Box>
    </Flex>
  )
}

function Detail() {
  return (
    <Flex
      display={{ base: 'none', md: 'flex' }}
      direction='column'
      width='46%'
      maxW='260px'
      flexShrink={0}
      borderLeftWidth='1px'
      borderColor={palette.border}
    >
      <Box px='4' py='3' borderBottomWidth='1px' borderColor={palette.borderSubtle}>
        <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.04em'>
          HD-1042
        </Text>
        <Text fontSize='xs' fontWeight='medium' color={palette.text} mt='1' lineHeight='1.35'>
          Refund missing from last invoice
        </Text>
      </Box>

      <Flex align='center' gap='2.5' px='4' py='3' borderBottomWidth='1px' borderColor={palette.borderSubtle}>
        <Flex
          boxSize='7'
          align='center'
          justify='center'
          borderRadius='full'
          bg={palette.ink}
          color={palette.textOnInk}
          fontSize='2xs'
          fontWeight='semibold'
          flexShrink={0}
        >
          AB
        </Flex>
        <Box minW='0'>
          <Text fontSize='2xs' color={palette.textFaint}>
            Assigned agent
          </Text>
          <Text fontSize='xs' color={palette.text} truncate>
            Avery Bennett
          </Text>
        </Box>
        <Flex ms='auto' color={palette.textMuted} aria-hidden>
          <ShieldCheck size={14} strokeWidth={1.9} />
        </Flex>
      </Flex>

      <Box px='4' py='3' flex='1' minW='0'>
        <Text fontSize='2xs' color={palette.textFaint} mb='2'>
          Conversation
        </Text>
        <Box
          borderWidth='1px'
          borderColor={palette.borderSubtle}
          borderRadius='l2'
          bg={palette.surfaceMuted}
          px='2.5'
          py='2'
        >
          <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
            “Happy to help — I've re-issued the credit and it should appear within a day.”
          </Text>
        </Box>
        <Box
          borderWidth='1px'
          borderColor={palette.borderSubtle}
          borderRadius='l2'
          bg={palette.surfaceMuted}
          px='2.5'
          py='2'
          mt='2'
        >
          <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
            “Thank you, that fixed it.”
          </Text>
        </Box>
      </Box>

      <Flex align='center' gap='2' px='4' py='3' borderTopWidth='1px' borderColor={palette.borderSubtle}>
        <Flex align='center' gap='1.5' color={palette.textFaint} fontSize='2xs'>
          <Paperclip size={11} strokeWidth={2} aria-hidden />
          Reply
        </Flex>
      </Flex>
    </Flex>
  )
}

function FloatingAgent() {
  return (
    <Flex
      display={{ base: 'none', lg: 'flex' }}
      position='absolute'
      top='-5'
      right='-4'
      className='hd-float'
      align='center'
      gap='2.5'
      px='3'
      py='2'
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      boxShadow={palette.shadowLg}
      zIndex='1'
    >
      <Flex
        boxSize='7'
        align='center'
        justify='center'
        borderRadius='full'
        bg={palette.ink}
        color={palette.textOnInk}
        fontSize='2xs'
        fontWeight='semibold'
        aria-hidden
      >
        AB
      </Flex>
      <Box>
        <Text fontSize='2xs' color={palette.textFaint} lineHeight='1.3'>
          Now assigned
        </Text>
        <Text fontSize='xs' color={palette.text} lineHeight='1.3'>
          Avery Bennett
        </Text>
      </Box>
    </Flex>
  )
}

function FloatingActivity() {
  return (
    <Box
      display={{ base: 'none', lg: 'block' }}
      position='absolute'
      bottom='-12'
      left='-5'
      className='hd-float-slow'
      px='3.5'
      py='3'
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      boxShadow={palette.shadowLg}
      minW='40'
      zIndex='1'
    >
      <Flex align='center' gap='2' mb='2'>
        <Box className='hd-pulse' boxSize='1.5' borderRadius='full' bg={palette.ink} aria-hidden />
        <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.04em'>
          Activity
        </Text>
      </Flex>
      <Text fontSize='2xs' color={palette.textSecondary} lineHeight='1.5'>
        Status changed to <Text as='span' color={palette.text}>In progress</Text>
      </Text>
      <Text fontSize='2xs' color={palette.textFaint} mt='1'>
        Comment added · just now
      </Text>
    </Box>
  )
}

export function ProductVisual() {
  return (
    <Box position='relative' w='full' maxW={{ base: 'full', lg: '640px' }} mx='auto'>
      <Box
        position='absolute'
        inset='-10%'
        className='hd-grid-bg hd-mask-fade'
        opacity={0.85}
        aria-hidden
      />

      <Box
        position='relative'
        bg={palette.surface}
        borderWidth='1px'
        borderColor={palette.border}
        borderRadius='l5'
        boxShadow={palette.shadowPanel}
        overflow='hidden'
        transform={{ base: 'none', lg: 'perspective(1600px) rotateX(4deg) rotateY(-7deg)' }}
        transformOrigin='70% 50%'
      >
        <WindowChrome />
        <Flex align='stretch' minH={{ base: '248px', md: '300px' }}>
          <Rail />
          <Queue />
          <Detail />
        </Flex>
      </Box>

      <FloatingAgent />
      <FloatingActivity />
    </Box>
  )
}
