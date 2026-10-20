import { Flex, Text } from '@chakra-ui/react'

import { palette } from '../theme/palette.ts'

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Flex align='center' gap='2.5' userSelect='none'>
      <Flex
        boxSize='7'
        borderRadius='l2'
        bg={palette.logo}
        color={palette.textOnInk}
        align='center'
        justify='center'
        flexShrink={0}
      >
        <img
          src='/deepseek_svg_20261019_8f1ee9.svg'
          alt='HelpDesk logo'
          width={28}
          height={28}
        />
      </Flex>

      {!compact ? (
        <Text
          fontSize='md'
          fontWeight='semibold'
          letterSpacing='-0.02em'
          color={palette.text}
        >
          HelpDesk
        </Text>
      ) : null}
    </Flex>
  )
}