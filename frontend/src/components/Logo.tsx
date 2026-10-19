import { Flex, Text } from '@chakra-ui/react'
import { LifeBuoy } from 'lucide-react'

import { palette } from '../theme/palette.ts'

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Flex align='center' gap='2.5' userSelect='none'>
      <Flex
        boxSize='7'
        borderRadius='l2'
        bg={palette.ink}
        color={palette.textOnInk}
        align='center'
        justify='center'
        flexShrink={0}
      >
        <LifeBuoy size={16} strokeWidth={2} aria-hidden />
      </Flex>
      {!compact ? (
        <Text fontSize='md' fontWeight='semibold' letterSpacing='-0.02em' color={palette.text}>
          HelpDesk
        </Text>
      ) : null}
    </Flex>
  )
}
