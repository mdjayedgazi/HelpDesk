import { Box, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { palette } from '../theme/palette.ts'

export function PageHeader({
  title,
  description,
  breadcrumb,
  actions,
  meta,
}: {
  title: ReactNode
  description?: ReactNode
  breadcrumb?: ReactNode
  actions?: ReactNode
  /** Optional supporting facts shown under the actions on wide screens. */
  meta?: ReactNode
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
        <Stack gap='1.5' minW='0'>
          <Heading
            as='h1'
            fontSize={{ base: 'xl', md: '2xl' }}
            fontWeight='semibold'
            letterSpacing='-0.025em'
            lineHeight='1.2'
            color={palette.text}
          >
            {title}
          </Heading>
          {description ? (
            <Text fontSize='sm' color={palette.textSecondary} maxW='2xl' lineHeight='1.6'>
              {description}
            </Text>
          ) : null}
          {meta ? <Box pt='1'>{meta}</Box> : null}
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

/** A breadcrumb trail. Renders a `<nav>` with a real ordered list. */
export function Breadcrumbs({
  items,
}: {
  items: Array<{ label: string; to?: string }>
}) {
  return (
    <Flex as='nav' aria-label='Breadcrumb' align='center' gap='1.5' fontSize='xs' wrap='wrap'>
      {items.map((item, index) => (
        <Flex key={`${item.label}-${index}`} align='center' gap='1.5'>
          {index > 0 ? (
            <Text as='span' color={palette.textFaint} aria-hidden>
              /
            </Text>
          ) : null}
          {item.to ? (
            <Link to={item.to} style={{ textDecoration: 'none' }}>
              <Text
                as='span'
                color={palette.textMuted}
                _hover={{ color: palette.text, textDecoration: 'underline' }}
              >
                {item.label}
              </Text>
            </Link>
          ) : (
            <Text as='span' color={palette.textSecondary} aria-current='page'>
              {item.label}
            </Text>
          )}
        </Flex>
      ))}
    </Flex>
  )
}
