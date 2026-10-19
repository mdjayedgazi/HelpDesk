import { Box, type BoxProps } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { gutter, widths } from '../theme/layout.ts'

type ContainerSize = 'content' | 'wide' | 'reading'

/**
 * The shared horizontal container.
 *
 * Every full-width band on the marketing page and the authenticated content
 * area wraps its contents in this component so left/right edges line up across
 * the whole product.
 */
export function Container({
  size = 'content',
  children,
  ...rest
}: Omit<BoxProps, 'children'> & { size?: ContainerSize; children?: ReactNode }) {
  return (
    <Box mx='auto' w='full' maxW={widths[size]} px={gutter} {...rest}>
      {children}
    </Box>
  )
}
