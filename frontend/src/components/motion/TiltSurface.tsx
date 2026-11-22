import { Box, type BoxProps } from '@chakra-ui/react'
import { useEffect, useRef, type ReactNode } from 'react'

import { prefersReducedMotion } from '../../theme/motion.ts'

const MAX_TILT = 4

/** Critically-damped spring used to smooth the tilt target. */
const STIFFNESS = 180
const DAMPING = 24
const MAX_DT = 1 / 30

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
 * - integrates a damped spring per axis inside rAF and writes the transform
 *   straight to the node, so pointer movement never causes a React re-render
 *   and the surface follows the cursor with a short, natural settle instead of
 *   a fixed CSS easing curve;
 * - resets to rest on pointer leave/blur and removes every listener on unmount.
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
    let last = 0

    // Target and current rotation in degrees.
    let targetX = 0
    let targetY = 0
    let rx = 0
    let ry = 0
    let vx = 0
    let vy = 0
    let active = false

    const write = () => {
      node.style.transform =
        rx === 0 && ry === 0
          ? ''
          : `perspective(1400px) rotateX(${rx.toFixed(3)}deg) rotateY(${ry.toFixed(3)}deg)`
    }

    const step = (now: number) => {
      frame = 0
      const dt = last === 0 ? 1 / 60 : Math.min(MAX_DT, (now - last) / 1000)
      last = now

      vx += (STIFFNESS * (targetX - rx) - DAMPING * vx) * dt
      vy += (STIFFNESS * (targetY - ry) - DAMPING * vy) * dt
      rx += vx * dt
      ry += vy * dt
      write()

      const settled =
        !active &&
        Math.abs(targetX - rx) < 0.01 &&
        Math.abs(targetY - ry) < 0.01 &&
        Math.abs(vx) < 0.01 &&
        Math.abs(vy) < 0.01
      if (settled) {
        rx = 0
        ry = 0
        vx = 0
        vy = 0
        write()
        return
      }
      frame = window.requestAnimationFrame(step)
    }

    const ensureFrame = () => {
      if (!frame) {
        last = 0
        frame = window.requestAnimationFrame(step)
      }
    }

    const onMove = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const px = (event.clientX - rect.left) / rect.width
      const py = (event.clientY - rect.top) / rect.height
      targetX = (0.5 - py) * MAX_TILT * 2
      targetY = (px - 0.5) * MAX_TILT * 2
      active = true
      ensureFrame()
    }

    const reset = () => {
      active = false
      targetX = 0
      targetY = 0
      ensureFrame()
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
      style={{
        transformStyle: 'preserve-3d',
        willChange: 'transform',
      }}
      {...rest}
    >
      {children}
    </Box>
  )
}
