import { Box, type BoxProps, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

/** A restrained white panel used to group related content. */
export function Surface({ children, ...rest }: BoxProps) {
  return (
    <Box
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      {...rest}
    >
      {children}
    </Box>
  )
}

export function SectionHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <Flex
      align={{ base: 'flex-start', sm: 'center' }}
      justify='space-between'
      gap='4'
      flexDirection={{ base: 'column', sm: 'row' }}
    >
      <Stack gap='0.5'>
        <Heading as='h2' fontSize='md' fontWeight='medium' color={palette.text}>
          {title}
        </Heading>
        {description ? (
          <Text fontSize='sm' color={palette.textSecondary}>
            {description}
          </Text>
        ) : null}
      </Stack>
      {actions ? <Flex gap='2'>{actions}</Flex> : null}
    </Flex>
  )
}
