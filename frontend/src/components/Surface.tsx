import { Box, type BoxProps, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import { forwardRef, type ReactNode } from 'react'

import { palette } from '../theme/palette.ts'
import { Reveal } from './Reveal.tsx'

/** A restrained white panel used to group related content. */
export const Surface = forwardRef<HTMLDivElement, BoxProps>(function Surface(
  { children, ...rest },
  ref,
) {
  return (
    <Box
      ref={ref}
      bg={palette.surface}
      borderWidth='1px'
      borderColor={palette.border}
      borderRadius='l3'
      {...rest}
    >
      {children}
    </Box>
  )
})

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
    <Reveal y={10}>
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
    </Reveal>
  )
}
