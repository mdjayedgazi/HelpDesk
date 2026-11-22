import { Box, type BoxProps } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { usePointerSpotlight } from '../hooks/usePointerSpotlight.ts'

/**
 * A restrained pointer-following highlight for interactive surfaces.
 *
 * Renders a soft radial light that is driven by CSS custom properties written
 * from a spring loop in `usePointerSpotlight`. It is purely decorative
 * (`aria-hidden`, `pointer-events: none`) and disabled for reduced motion,
 * touch pointers and narrow viewports, so it can never move content, capture a
 * click or cost anything on a phone.
 *
 * The light is painted as an overlay above the card surface: the card itself is
 * an opaque panel, so a glow behind it would never be seen. At the default
 * intensity the tint is roughly 10% of the accent at its centre and fades to
 * nothing at the edge — enough to feel responsive, far too little to affect
 * text contrast.
 *
 * Use it on cards that already signal interactivity on hover; it is not meant
 * for inert data surfaces.
 */
export function PointerHighlight({
  children,
  intensity = 0.35,
  radius = 240,
  ...rest
}: BoxProps & {
  children?: ReactNode
  /** Peak overlay opacity at the pointer, 0–1. Keep low for data cards (≈0.2). */
  intensity?: number
  /** Highlight radius in px. */
  radius?: number
}) {
  const ref = usePointerSpotlight<HTMLDivElement>({ intensity, radius })

  return (
    <Box ref={ref} position='relative' isolation='isolate' className='hd-pointer-host' {...rest}>
      <Box position='relative' zIndex='1'>
        {children}
      </Box>
      <Box
        aria-hidden
        pointerEvents='none'
        position='absolute'
        inset='0'
        borderRadius='inherit'
        zIndex='2'
        opacity='var(--hd-pointer-glow, 0)'
        transition='opacity var(--hd-dur-2) var(--hd-ease)'
        background='radial-gradient(var(--hd-pointer-radius, 240px) circle at var(--hd-pointer-x, 50%) var(--hd-pointer-y, 50%), var(--hd-spot), transparent 68%)'
      />
    </Box>
  )
}
