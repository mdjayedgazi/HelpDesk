import { Box, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

export function PageHeader({
  title,
  description,
  breadcrumb,
  actions,
}: {
  title: ReactNode
  description?: ReactNode
  breadcrumb?: ReactNode
  actions?: ReactNode
}) {
  return (
    <Stack gap='4' borderBottomWidth='1px' borderColor={palette.border} pb='6' mb='6'>
      {breadcrumb ? <Box>{breadcrumb}</Box> : null}
      <Flex
        align={{ base: 'flex-start', md: 'center' }}
        justify='space-between'
        gap='4'
        flexDirection={{ base: 'column', md: 'row' }}
      >
        <Stack gap='1.5'>
          <Heading
            as='h1'
            fontSize={{ base: 'xl', md: '2xl' }}
            fontWeight='medium'
            letterSpacing='-0.02em'
            color={palette.text}
          >
            {title}
          </Heading>
          {description ? (
            <Text fontSize='sm' color={palette.textSecondary} maxW='2xl'>
              {description}
            </Text>
          ) : null}
        </Stack>
        {actions ? (
          <Flex gap='2' flexWrap='wrap' flexShrink={0}>
            {actions}
          </Flex>
        ) : null}
      </Flex>
    </Stack>
  )
}
