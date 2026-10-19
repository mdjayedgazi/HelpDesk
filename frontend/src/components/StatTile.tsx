import { Box, Flex, Text } from '@chakra-ui/react'
import type { LucideIcon } from 'lucide-react'

import { palette } from '../theme/palette.ts'
import { Surface } from './Surface.tsx'

export function StatTile({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: number | string
  hint?: string
  icon?: LucideIcon
}) {
  return (
    <Surface p='5'>
      <Flex justify='space-between' align='flex-start' gap='3'>
        <Text fontSize='xs' color={palette.textMuted} letterSpacing='0.02em'>
          {label}
        </Text>
        {Icon ? (
          <Box color={palette.textFaint}>
            <Icon size={15} strokeWidth={1.75} aria-hidden />
          </Box>
        ) : null}
      </Flex>
      <Text
        mt='3'
        fontSize='3xl'
        fontWeight='medium'
        letterSpacing='-0.03em'
        lineHeight='1'
        color={palette.text}
        fontVariantNumeric='tabular-nums'
      >
        {value}
      </Text>
      {hint ? (
        <Text mt='2' fontSize='xs' color={palette.textMuted}>
          {hint}
        </Text>
      ) : null}
    </Surface>
  )
}

export function BreakdownBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <Box>
      <Flex justify='space-between' align='baseline' mb='1.5'>
        <Text fontSize='sm' color={palette.textSecondary}>
          {label}
        </Text>
        <Text fontSize='sm' color={palette.text} fontVariantNumeric='tabular-nums'>
          {value}
        </Text>
      </Flex>
      <Box height='1.5' borderRadius='full' bg={palette.inset} overflow='hidden'>
        <Box
          height='100%'
          width={`${pct}%`}
          bg={palette.ink}
          borderRadius='full'
          transition='width 0.3s ease'
        />
      </Box>
    </Box>
  )
}
