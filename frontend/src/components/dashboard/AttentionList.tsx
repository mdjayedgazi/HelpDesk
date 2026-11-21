import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { ArrowUpRight, CheckCircle2, CircleAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { AttentionItem } from '../../lib/analytics.ts'
import { palette } from '../../theme/palette.ts'
import { tones } from '../../theme/statusTone.ts'
import { Surface } from '../Surface.tsx'

/**
 * "What needs attention" strip.
 *
 * Each row is a real counter with a deep link to the filtered ticket list that
 * explains it. When the queue is healthy the strip turns into a positive,
 * low-emphasis confirmation instead of showing empty metrics.
 */
export function AttentionList({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return (
      <Surface p='4'>
        <Flex align='center' gap='3'>
          <Flex
            boxSize='8'
            align='center'
            justify='center'
            borderRadius='full'
            bg={tones.success.soft}
            color={tones.success.solid}
            flexShrink={0}
          >
            <CheckCircle2 size={16} strokeWidth={2} aria-hidden />
          </Flex>
          <Box minW='0'>
            <Text fontSize='sm' fontWeight='medium' color={palette.text}>
              Nothing is waiting on the team
            </Text>
            <Text fontSize='xs' color={palette.textMuted}>
              No urgent, unassigned or stale tickets right now.
            </Text>
          </Box>
        </Flex>
      </Surface>
    )
  }

  return (
    <Surface p='0' overflow='hidden'>
      <Flex
        px='4'
        py='3'
        borderBottomWidth='1px'
        borderColor={palette.borderSubtle}
        align='center'
        gap='2'
      >
        <CircleAlert size={14} color={palette.textMuted} aria-hidden />
        <Text fontSize='xs' fontWeight='semibold' color={palette.text} letterSpacing='0.01em'>
          Needs attention
        </Text>
      </Flex>
      <Box as='ul' listStyleType='none' m='0' p='0'>
        {items.map((item) => {
          const tone = tones[item.tone]
          const Icon: LucideIcon = CircleAlert
          return (
            <Box as='li' key={item.key} borderBottomWidth='1px' borderColor={palette.borderSubtle}>
              <Flex
                asChild
                align='center'
                gap='3'
                px='4'
                py='3'
                textDecoration='none'
                transition='background var(--hd-dur-1) var(--hd-ease)'
                _hover={{ bg: palette.hover }}
                _focusVisible={{
                  outline: '2px solid',
                  outlineColor: palette.focus,
                  outlineOffset: '-2px',
                }}
              >
                <Link to={item.to}>
                  <Flex
                    boxSize='7'
                    align='center'
                    justify='center'
                    borderRadius='l2'
                    bg={tone.soft}
                    color={tone.solid}
                    flexShrink={0}
                  >
                    <Icon size={13} strokeWidth={2.2} aria-hidden />
                  </Flex>
                  <Box minW='0' flex='1'>
                    <Text fontSize='sm' color={palette.text} fontWeight='medium' truncate>
                      {item.label}
                    </Text>
                    <Text fontSize='2xs' color={palette.textMuted} truncate>
                      {item.detail}
                    </Text>
                  </Box>
                  <Text
                    fontSize='sm'
                    fontWeight='semibold'
                    color={tone.solid}
                    fontVariantNumeric='tabular-nums'
                  >
                    {item.value}
                  </Text>
                  <ArrowUpRight size={14} color={palette.textFaint} aria-hidden />
                </Link>
              </Flex>
            </Box>
          )
        })}
      </Box>
      <Flex px='4' py='2.5' borderTopWidth='1px' borderColor={palette.borderSubtle}>
        <Text fontSize='2xs' color={palette.textFaint}>
          Counts are exact. Links open the closest matching list; the ticket API
          filters one value at a time and has no unassigned filter, so a linked view
          is approximate.
        </Text>
      </Flex>
    </Surface>
  )
}

/**
 * Team workload: one row per active agent, with a proportional bar for active
 * tickets and explicit counts for urgent and resolved work.
 *
 * Agents are ordered by live workload only. The copy avoids ranking people by
 * raw output because resolution counts are not normalized for shift length or
 * ticket difficulty.
 */
export function WorkloadList({
  entries,
  limit = 8,
}: {
  entries: Array<{
    user_id: string
    full_name: string
    active_tickets: number
    urgent_tickets: number
    resolved_tickets: number
  }>
  limit?: number
}) {
  if (entries.length === 0) {
    return (
      <Text fontSize='xs' color={palette.textMuted}>
        No active agents with assigned tickets.
      </Text>
    )
  }

  const visible = entries.slice(0, limit)
  const max = Math.max(1, ...visible.map((entry) => entry.active_tickets))

  return (
    <Stack gap='0' as='ul' listStyleType='none' m='0' p='0'>
      {visible.map((entry) => {
        const widthPct = Math.round((entry.active_tickets / max) * 100)
        return (
          <Flex
            as='li'
            key={entry.user_id}
            direction='column'
            gap='1.5'
            py='2.5'
            borderBottomWidth='1px'
            borderColor={palette.borderSubtle}
            _last={{ borderBottomWidth: 0 }}
          >
            <Flex align='center' gap='3' justify='space-between'>
              <Text fontSize='xs' color={palette.text} fontWeight='medium' truncate minW='0'>
                {entry.full_name}
              </Text>
              <Flex align='center' gap='3' flexShrink={0}>
                {entry.urgent_tickets > 0 ? (
                  <Text fontSize='2xs' color={palette.semantic.danger} fontWeight='medium'>
                    {entry.urgent_tickets} urgent
                  </Text>
                ) : null}
                <Text
                  fontSize='2xs'
                  color={palette.textMuted}
                  fontVariantNumeric='tabular-nums'
                  minW='16'
                  textAlign='right'
                >
                  {entry.resolved_tickets} resolved
                </Text>
                <Text
                  fontSize='xs'
                  color={palette.text}
                  fontWeight='semibold'
                  fontVariantNumeric='tabular-nums'
                  minW='6'
                  textAlign='right'
                >
                  {entry.active_tickets}
                </Text>
              </Flex>
            </Flex>
            <Box height='1.5' borderRadius='full' bg={palette.inset} overflow='hidden'>
              <Box
                height='100%'
                width={`${widthPct}%`}
                bg={entry.urgent_tickets > 0 ? palette.semantic.danger : palette.text}
                borderRadius='full'
                transition='width var(--hd-dur-3) var(--hd-ease-out)'
              />
            </Box>
          </Flex>
        )
      })}
    </Stack>
  )
}
