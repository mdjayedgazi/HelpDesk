import { Box, Flex, Text } from '@chakra-ui/react'
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Inbox,
  LayoutDashboard,
  MessageSquare,
  Settings2,
  Ticket,
  UserRound,
} from 'lucide-react'

import { palette } from '../../theme/palette.ts'
import { tones } from '../../theme/statusTone.ts'
import { FloatingElement } from '../motion/FloatingElement.tsx'
import { TiltSurface } from '../motion/TiltSurface.tsx'

/**
 * Illustrative product visual for the hero.
 *
 * This is a *sample* of the real workspace composition — metric row, volume
 * trend, status split and the ticket queue — drawn from the same layout
 * vocabulary and Tailwind/Chakra tokens as the product itself. Every number is
 * fictional sample data, clearly labelled as such; it never calls a protected
 * API and is never presented as live operational data.
 */

const queue = [
  { ref: 'HD-1042', subject: 'Refund missing from last invoice', status: 'In progress', tone: 'info' as const, active: true },
  { ref: 'HD-1039', subject: 'Reset password link has expired', status: 'Open', tone: 'info' as const },
  { ref: 'HD-1031', subject: 'Dashboard slow after CSV export', status: 'Waiting on customer', tone: 'warning' as const },
  { ref: 'HD-1027', subject: 'Add three seats for design team', status: 'Resolved', tone: 'success' as const },
]

const series = [4, 7, 5, 9, 8, 12, 10, 14, 11, 15, 13, 17, 15, 19]

function WindowChrome() {
  return (
    <Flex
      align='center'
      gap='3'
      px='4'
      height='10'
      borderBottomWidth='1px'
      borderColor={palette.border}
      bg={palette.surfaceMuted}
    >
      <Flex gap='1.5' aria-hidden>
        <Box boxSize='2.5' borderRadius='full' bg={palette.borderStrong} />
        <Box boxSize='2.5' borderRadius='full' bg={palette.borderStrong} />
        <Box boxSize='2.5' borderRadius='full' bg={palette.border} />
      </Flex>
      <Text fontSize='2xs' color={palette.textMuted} letterSpacing='0.02em' truncate flex='1'>
        HelpDesk · Support operations
      </Text>
      <Box
        px='2'
        py='0.5'
        borderRadius='full'
        borderWidth='1px'
        borderColor={palette.border}
        bg={palette.surface}
      >
        <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.04em'>
          SAMPLE DATA
        </Text>
      </Box>
    </Flex>
  )
}

function Rail() {
  const items = [LayoutDashboard, Ticket, MessageSquare, UserRound, Settings2]
  return (
    <Flex
      display={{ base: 'none', md: 'flex' }}
      direction='column'
      align='center'
      gap='1.5'
      py='3'
      px='1.5'
      width='10'
      borderRightWidth='1px'
      borderColor={palette.borderSubtle}
      bg={palette.surfaceMuted}
      flexShrink={0}
    >
      {items.map((Icon, index) => (
        <Flex
          key={index}
          boxSize='7'
          align='center'
          justify='center'
          borderRadius='l2'
          bg={index === 0 ? palette.ink : 'transparent'}
          color={index === 0 ? palette.textOnInk : palette.textFaint}
          aria-hidden
        >
          <Icon size={14} strokeWidth={1.9} />
        </Flex>
      ))}
    </Flex>
  )
}

function TrendSpark() {
  const max = Math.max(...series)
  const width = 132
  const height = 36
  const points = series.map((value, index) => ({
    x: (index / (series.length - 1)) * width,
    y: height - (value / max) * height,
  }))
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width='100%'
      height={height}
      preserveAspectRatio='none'
      aria-hidden='true'
    >
      <path
        d={path}
        fill='none'
        stroke={palette.chart[0]}
        strokeWidth='1.5'
        strokeLinecap='round'
        strokeLinejoin='round'
        vectorEffect='non-scaling-stroke'
      />
    </svg>
  )
}

function Metrics() {
  const tiles = [
    { label: 'Total', value: '1,284' },
    { label: 'Open', value: '86', tone: 'info' as const },
    { label: 'Waiting', value: '24', tone: 'warning' as const },
    { label: 'Resolved', value: '1,102', tone: 'success' as const },
  ]
  return (
    <Box display='grid' gridTemplateColumns='repeat(4, minmax(0, 1fr))' gap='2'>
      {tiles.map((tile) => (
        <Box
          key={tile.label}
          borderWidth='1px'
          borderColor={palette.border}
          borderRadius='l2'
          px='2.5'
          py='2'
          minW='0'
        >
          <Flex align='center' gap='1' mb='1'>
            <Box
              boxSize='1.5'
              borderRadius='full'
              bg={tile.tone ? tones[tile.tone].solid : palette.textMuted}
              aria-hidden
            />
            <Text fontSize='2xs' color={palette.textMuted} truncate>
              {tile.label}
            </Text>
          </Flex>
          <Text fontSize='md' fontWeight='semibold' color={palette.text} letterSpacing='-0.02em'>
            {tile.value}
          </Text>
        </Box>
      ))}
    </Box>
  )
}

function StatusSplit() {
  const total = 86 + 34 + 24 + 1102 + 38
  const segments = [
    { label: 'Open', value: 86, color: tones.info.solid },
    { label: 'In progress', value: 34, color: palette.chart[2] },
    { label: 'Waiting', value: 24, color: tones.warning.solid },
    { label: 'Resolved', value: 1102, color: tones.success.solid },
    { label: 'Closed', value: 38, color: palette.textFaint },
  ]
  return (
    <Box>
      <Text fontSize='2xs' color={palette.textMuted} mb='2'>
        Status composition
      </Text>
      <Flex height='2' borderRadius='full' overflow='hidden' gap='0.5' mb='2.5'>
        {segments.map((segment) => (
          <Box
            key={segment.label}
            height='100%'
            width={`${(segment.value / total) * 100}%`}
            bg={segment.color}
            aria-hidden
          />
        ))}
      </Flex>
      <Flex gap='3' wrap='wrap'>
        {segments.slice(0, 4).map((segment) => (
          <Flex key={segment.label} align='center' gap='1.5'>
            <Box boxSize='1.5' borderRadius='full' bg={segment.color} aria-hidden />
            <Text fontSize='2xs' color={palette.textFaint}>
              {segment.label}
            </Text>
            <Text fontSize='2xs' color={palette.text} fontWeight='medium'>
              {segment.value}
            </Text>
          </Flex>
        ))}
      </Flex>
    </Box>
  )
}

function Queue() {
  return (
    <Flex direction='column' minW='0'>
      <Flex align='center' justify='space-between' gap='2' mb='2'>
        <Text fontSize='xs' fontWeight='semibold' color={palette.text}>
          Live queue
        </Text>
        <Text fontSize='2xs' color={palette.textFaint}>
          Sorted by priority
        </Text>
      </Flex>
      <Box borderWidth='1px' borderColor={palette.border} borderRadius='l2' overflow='hidden'>
        {queue.map((row, index) => (
          <Flex
            key={row.ref}
            align='center'
            gap='2.5'
            px='2.5'
            py='2'
            borderBottomWidth={index === queue.length - 1 ? '0' : '1px'}
            borderColor={palette.borderSubtle}
            bg={row.active ? palette.hover : 'transparent'}
          >
            <Box boxSize='1.5' borderRadius='full' bg={tones[row.tone].solid} flexShrink={0} aria-hidden />
            <Box minW='0' flex='1'>
              <Text
                fontSize='2xs'
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
            <ArrowRight size={11} color={palette.textFaint} aria-hidden />
          </Flex>
        ))}
      </Box>
    </Flex>
  )
}

export function ProductVisual() {
  return (
    <Box
      position='relative'
      w='full'
      maxW={{ base: 'full', lg: '640px' }}
      mx='auto'
    >
      <Box
        position='absolute'
        inset='-8%'
        className='hd-grid-bg hd-mask-fade'
        opacity={0.85}
        aria-hidden
      />

      <Box position='relative' style={{ perspective: '1400px' }}>
        <TiltSurface>
          <FloatingElement distance={7} duration={7800} delay={0}>
            <Box
              position='relative'
              bg={palette.surface}
              borderWidth='1px'
              borderColor={palette.border}
              borderRadius='l4'
              boxShadow={palette.shadowPanel}
              overflow='hidden'
            >
              <WindowChrome />
              <Flex align='stretch'>
                <Rail />
                <Box flex='1' minW='0' p={{ base: '3', md: '4' }}>
                  <Flex align='center' justify='space-between' gap='2' mb='3'>
                    <Box minW='0'>
                      <Text fontSize='2xs' color={palette.textFaint}>
                        Dashboard · sample
                      </Text>
                      <Text
                        fontSize='xs'
                        fontWeight='semibold'
                        color={palette.text}
                        letterSpacing='-0.01em'
                      >
                        Support operations
                      </Text>
                    </Box>
                    <Flex
                      align='center'
                      gap='1.5'
                      px='2'
                      py='1'
                      borderWidth='1px'
                      borderColor={palette.border}
                      borderRadius='full'
                      flexShrink={0}
                    >
                      <CheckCircle2
                        size={10}
                        strokeWidth={2.4}
                        color={tones.success.solid}
                        aria-hidden
                      />
                      <Text fontSize='2xs' color={palette.textMuted}>
                        Healthy
                      </Text>
                    </Flex>
                  </Flex>

                  <Metrics />

                  <Flex
                    display={{ base: 'none', sm: 'grid' }}
                    gridTemplateColumns='minmax(0, 1.2fr) minmax(0, 1fr)'
                    gap='2'
                    mt='2'
                  >
                    <Box
                      borderWidth='1px'
                      borderColor={palette.border}
                      borderRadius='l2'
                      p='2.5'
                      minW='0'
                    >
                      <Flex align='center' justify='space-between' gap='2' mb='1.5'>
                        <Text fontSize='2xs' color={palette.textMuted}>
                          Ticket volume · 14 days
                        </Text>
                        <Flex align='center' gap='1'>
                          <Clock size={10} color={palette.textFaint} aria-hidden />
                          <Text fontSize='2xs' color={palette.textFaint}>
                            Daily
                          </Text>
                        </Flex>
                      </Flex>
                      <TrendSpark />
                    </Box>
                    <Box
                      borderWidth='1px'
                      borderColor={palette.border}
                      borderRadius='l2'
                      p='2.5'
                      minW='0'
                    >
                      <StatusSplit />
                    </Box>
                  </Flex>

                  <Box mt='2'>
                    <Queue />
                  </Box>
                </Box>
              </Flex>
            </Box>
          </FloatingElement>
        </TiltSurface>

        {/* Layered satellite panels.
            They hang below the dashboard's bottom edge in a staggered shelf, so
            the composition reads as three planes at different depths while no
            label, number or sample-data marker inside the dashboard is ever
            covered. Each drifts on its own slower cycle, which is what makes
            the depth legible. Hidden below `xl`, where there is no room for a
            shelf without overlapping content. */}
        <FloatingElement
          display={{ base: 'none', xl: 'block' }}
          position='absolute'
          bottom='-104px'
          left='0'
          distance={5}
          duration={8600}
          delay={900}
          aria-hidden
        >
          <Box
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            boxShadow={palette.shadowLg}
            px='3'
            py='2.5'
            width='164px'
          >
            <Flex align='center' justify='space-between' gap='2'>
              <Text fontSize='2xs' color={palette.textFaint}>
                Resolved today
              </Text>
              <Text
                fontSize='2xs'
                color={palette.textFaint}
                letterSpacing='0.04em'
              >
                SAMPLE
              </Text>
            </Flex>
            <Text
              fontSize='lg'
              fontWeight='semibold'
              color={palette.text}
              letterSpacing='-0.02em'
              fontVariantNumeric='tabular-nums'
              mt='1'
            >
              38
            </Text>
            <Flex align='center' gap='1.5' mt='1.5'>
              <Box boxSize='1.5' borderRadius='full' bg={tones.success.solid} aria-hidden />
              <Text fontSize='2xs' color={palette.textMuted}>
                Trending up
              </Text>
            </Flex>
          </Box>
        </FloatingElement>

        <FloatingElement
          display={{ base: 'none', xl: 'block' }}
          position='absolute'
          bottom='-78px'
          right='0'
          distance={6}
          duration={7200}
          delay={1600}
          aria-hidden
        >
          <Box
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            boxShadow={palette.shadowLg}
            px='3'
            py='2.5'
            width='178px'
          >
            <Flex align='center' justify='space-between' gap='2' mb='2'>
              <Text fontSize='2xs' color={palette.textFaint}>
                First response
              </Text>
              <Text fontSize='2xs' color={palette.textFaint} letterSpacing='0.04em'>
                SAMPLE
              </Text>
            </Flex>
            <Flex align='baseline' gap='1'>
              <Text
                fontSize='lg'
                fontWeight='semibold'
                color={palette.text}
                letterSpacing='-0.02em'
                fontVariantNumeric='tabular-nums'
              >
                92
              </Text>
              <Text fontSize='2xs' color={palette.textMuted}>
                % within target
              </Text>
            </Flex>
            <Box height='1.5' borderRadius='full' bg={palette.inset} overflow='hidden' mt='2'>
              <Box
                height='100%'
                width='92%'
                borderRadius='full'
                bg={palette.accent}
                aria-hidden
              />
            </Box>
          </Box>
        </FloatingElement>

        <FloatingElement
          display={{ base: 'none', lg: 'block' }}
          position='absolute'
          bottom='-152px'
          left='34%'
          distance={4}
          duration={6400}
          delay={400}
          aria-hidden
        >
          <Flex
            align='center'
            gap='2'
            px='2.5'
            py='1.5'
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            boxShadow={palette.shadowMd}
          >
            <Inbox size={12} color={palette.textMuted} aria-hidden />
            <Text fontSize='2xs' color={palette.textSecondary}>
              Sample workspace preview
            </Text>
          </Flex>
        </FloatingElement>
      </Box>
    </Box>
  )
}
