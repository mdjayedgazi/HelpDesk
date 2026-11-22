import { Box, type BoxProps } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { gutter, widths, workspaceGutter } from '../theme/layout.ts'

type ContainerSize = 'workspace' | 'content' | 'wide' | 'reading' | 'detail'

/**
 * The shared horizontal container.
 *
 * Every full-width band on the marketing page and the authenticated content
 * area wraps its contents in this component so left/right edges line up across
 * the whole product.
 *
 * The `workspace` size is the authenticated app shell: it fills the main
 * column (minus the sidebar) and only caps on very wide displays, so the
 * dashboards and tables use the horizontal space they actually have.
 */
export function Container({
  size = 'content',
  children,
  ...rest
}: Omit<BoxProps, 'children'> & { size?: ContainerSize; children?: ReactNode }) {
  return (
    <Box
      mx='auto'
      w='full'
      maxW={widths[size]}
      px={size === 'workspace' ? workspaceGutter : gutter}
      {...rest}
    >
      {children}
    </Box>
  )
}
