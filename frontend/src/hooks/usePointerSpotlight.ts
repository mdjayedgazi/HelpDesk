import { useEffect, useRef } from 'react'

import { prefersReducedMotion } from '../theme/motion.ts'

/**
 * Options shared by every pointer-responsive surface.
 *
 * The defaults are deliberately conservative: a few pixels of travel, a very
 * soft highlight and a short spring. The point is to make a card feel alive
 * under the cursor, not to turn the dashboard into a toy.
 */
export interface PointerSpotlightOptions {
  /** Peak overlay opacity at the pointer, 0–1. Default 0.35. */
  intensity?: number
  /** Radius of the highlight in px. Default 220. */
  radius?: number
  /** Extra transform travel in px (0 disables the lift). Default 0. */
  lift?: number
  /** Skip on coarse pointers. Default true. */
  finePointerOnly?: boolean
  /** Skip below this viewport width in px. Default 1024. */
  minViewportWidth?: number
}

/**
 * Critically-damped spring parameters, tuned by feel.
 *
 * A real spring is integrated per frame from the pointer target, so the
 * highlight follows the cursor with a slight, natural lag instead of snapping
 * or easing on a fixed curve. `stiffness` 170 / `damping` 26 settles in roughly
 * 160 ms with no visible overshoot.
 */
const STIFFNESS = 170
const DAMPING = 26
const MAX_DT = 1 / 30

/**
 * Attach a softly spring-followed highlight to a DOM node.
 *
 * Writes `--hd-pointer-x`, `--hd-pointer-y` (percentages inside the node),
 * `--hd-pointer-glow` (0–1) and, when `lift` is enabled, a tiny
 * `translate3d(...)` straight to the element's style inside a single
 * requestAnimationFrame loop. It never calls React state setters, so moving the
 * pointer cannot re-render the card or its charts.
 *
 * The effect is disabled for reduced-motion users, coarse pointers and narrow
 * viewports, and on unmount it cancels the frame, removes its listeners and
 * clears the inline values it wrote.
 */
export function usePointerSpotlight<T extends HTMLElement = HTMLDivElement>({
  intensity = 0.35,
  radius = 220,
  lift = 0,
  finePointerOnly = true,
  minViewportWidth = 1024,
}: PointerSpotlightOptions = {}) {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (prefersReducedMotion()) return
    if (typeof window.matchMedia !== 'function') return
    if (finePointerOnly && !window.matchMedia('(pointer: fine)').matches) return
    if (window.matchMedia(`(max-width: ${minViewportWidth - 1}px)`).matches) return

    let frame = 0
    let rafId = 0
    let last = 0

    // Pointer target and spring state, all in a 0–1 space inside the node.
    let targetX = 0.5
    let targetY = 0.5
    let x = 0.5
    let y = 0.5
    let vx = 0
    let vy = 0
    let targetGlow = 0
    let glow = 0
    let vGlow = 0
    let active = false

    const step = (now: number) => {
      frame = 0
      const dt = last === 0 ? 1 / 60 : Math.min(MAX_DT, (now - last) / 1000)
      last = now

      // Semi-implicit Euler integration of a damped spring per axis.
      vx += (STIFFNESS * (targetX - x) - DAMPING * vx) * dt
      vy += (STIFFNESS * (targetY - y) - DAMPING * vy) * dt
      vGlow += (STIFFNESS * (targetGlow - glow) - DAMPING * vGlow) * dt
      x += vx * dt
      y += vy * dt
      glow += vGlow * dt

      node.style.setProperty('--hd-pointer-x', `${(x * 100).toFixed(2)}%`)
      node.style.setProperty('--hd-pointer-y', `${(y * 100).toFixed(2)}%`)
      node.style.setProperty('--hd-pointer-glow', `${(glow * intensity).toFixed(4)}`)
      node.style.setProperty('--hd-pointer-radius', `${radius}px`)
      if (lift > 0) {
        node.style.setProperty(
          '--hd-pointer-lift',
          `${((x - 0.5) * lift).toFixed(2)}px ${((y - 0.5) * lift).toFixed(2)}px`,
        )
      }

      const settled =
        !active &&
        Math.abs(targetX - x) < 0.001 &&
        Math.abs(targetY - y) < 0.001 &&
        Math.abs(targetGlow - glow) < 0.001 &&
        Math.abs(vx) < 0.001 &&
        Math.abs(vy) < 0.001 &&
        Math.abs(vGlow) < 0.001

      if (settled) {
        // Park at exactly the resting values so a hover card can never leave a
        // faint glow behind.
        node.style.setProperty('--hd-pointer-glow', '0')
        node.style.setProperty('--hd-pointer-lift', '0px 0px')
        return
      }

      rafId = window.requestAnimationFrame(step)
      frame = rafId
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
      targetX = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
      targetY = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
      targetGlow = 1
      active = true
      ensureFrame()
    }

    const onLeave = () => {
      active = false
      targetGlow = 0
      // Return the highlight to the centre while it fades, which reads as the
      // light easing away rather than sliding off the card's nearest edge.
      targetX = 0.5
      targetY = 0.5
      ensureFrame()
    }

    node.addEventListener('pointermove', onMove)
    node.addEventListener('pointerenter', onMove)
    node.addEventListener('pointerleave', onLeave)

    return () => {
      node.removeEventListener('pointermove', onMove)
      node.removeEventListener('pointerenter', onMove)
      node.removeEventListener('pointerleave', onLeave)
      if (rafId) window.cancelAnimationFrame(rafId)
      if (frame) window.cancelAnimationFrame(frame)
      for (const property of [
        '--hd-pointer-x',
        '--hd-pointer-y',
        '--hd-pointer-glow',
        '--hd-pointer-radius',
        '--hd-pointer-lift',
      ]) {
        node.style.removeProperty(property)
      }
    }
  }, [intensity, radius, lift, finePointerOnly, minViewportWidth])

  return ref
}
