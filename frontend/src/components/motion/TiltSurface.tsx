import { Box, type BoxProps } from '@chakra-ui/react'
import { useEffect, useRef, type ReactNode } from 'react'

import { prefersReducedMotion } from '../../theme/motion.ts'

const MAX_TILT = 4

/**
 * Very small pointer-responsive 3D tilt.
 *
 * Used only for the landing-page product surface, where a few degrees of
 * perspective helps the flat illustration read as a physical interface. It is
 * deliberately conservative:
 *
 * - max 4° of rotation, so nothing distorts;
 * - only attaches on fine pointers at >= 1024 px, so touch and mobile are
 *   unaffected;
 * - does nothing when reduced motion is requested;
 * - writes transforms straight to the node inside rAF, so pointer movement
 *   never causes a React re-render;
 * - resets on pointer leave/blur and removes every listener on unmount.
 */
export function TiltSurface({
  children,
  ...rest
}: BoxProps & { children?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (prefersReducedMotion()) return
    if (typeof window.matchMedia !== 'function') return
    if (!window.matchMedia('(pointer: fine)').matches) return
    if (window.matchMedia('(max-width: 1023px)').matches) return

    let frame = 0
    let pending: { rotateX: number; rotateY: number } | null = null

    const apply = () => {
      frame = 0
      if (!pending) return
      node.style.transform = `perspective(1400px) rotateX(${pending.rotateX}deg) rotateY(${pending.rotateY}deg)`
    }

    const onMove = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const px = (event.clientX - rect.left) / rect.width
      const py = (event.clientY - rect.top) / rect.height
      pending = {
        rotateX: (0.5 - py) * MAX_TILT * 2,
        rotateY: (px - 0.5) * MAX_TILT * 2,
      }
      if (!frame) frame = window.requestAnimationFrame(apply)
    }

    const reset = () => {
      pending = null
      if (frame) {
        window.cancelAnimationFrame(frame)
        frame = 0
      }
      node.style.transform = ''
    }

    node.addEventListener('pointermove', onMove)
    node.addEventListener('pointerleave', reset)
    node.addEventListener('blur', reset)

    return () => {
      node.removeEventListener('pointermove', onMove)
      node.removeEventListener('pointerleave', reset)
      node.removeEventListener('blur', reset)
      if (frame) window.cancelAnimationFrame(frame)
      node.style.transform = ''
    }
  }, [])

  return (
    <Box
      ref={ref}
      style={{ transformStyle: 'preserve-3d', transition: 'transform 180ms cubic-bezier(0.22, 0.61, 0.36, 1)' }}
      {...rest}
    >
      {children}
    </Box>
  )
}
