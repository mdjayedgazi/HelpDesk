import { Box, Button, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import { useAuth } from '@clerk/react'
import { ArrowRight, CheckCircle2, Compass } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'

import { site } from '../../lib/site.ts'
import { stagger } from '../../theme/motion.ts'
import { palette } from '../../theme/palette.ts'
import { Container } from '../Container.tsx'
import { Reveal } from '../Reveal.tsx'
import { ProductVisual } from './ProductVisual.tsx'
import { Eyebrow } from './primitives.tsx'

const primaryButtonProps = {
  bg: palette.ink,
  color: palette.textOnInk,
  height: '11',
  px: '5',
  transition: 'background var(--hd-dur-1) var(--hd-ease), transform var(--hd-dur-1) var(--hd-ease)',
  _hover: { bg: palette.inkHover },
  _active: { transform: 'translateY(1px)' },
} as const

const secondaryButtonProps = {
  variant: 'outline',
  borderColor: palette.border,
  color: palette.text,
  bg: palette.surface,
  height: '11',
  px: '5',
  transition:
    'background var(--hd-dur-1) var(--hd-ease), border-color var(--hd-dur-1) var(--hd-ease), transform var(--hd-dur-1) var(--hd-ease)',
  _hover: { bg: palette.hover, borderColor: palette.borderStrong },
  _active: { transform: 'translateY(1px)' },
} as const

const proofPoints = [
  'Tickets, statuses and priorities',
  'Assignment and shared queues',
  'Internal notes kept internal',
]

/**
 * Landing hero.
 *
 * The copy enters in a single readable rhythm — label, heading, description,
 * actions, proof points — with a 70 ms beat between steps, so the eye is led
 * down the page instead of being hit with one block. The product visual follows
 * slightly later and then drifts on its own, which is the only continuous
 * motion on the page.
 *
 * Every element is fully readable on the first frame; the animation only
 * softens the arrival. Under `prefers-reduced-motion` the `Reveal` component
 * renders the final state immediately.
 */
export function HeroSection() {
  const { isLoaded, isSignedIn } = useAuth()
  const signedIn = isLoaded && isSignedIn

  return (
    <Box
      as='section'
      aria-labelledby='hero-heading'
      position='relative'
      overflow='hidden'
      pt={{ base: '12', md: '18', lg: '20' }}
      pb={{ base: '16', lg: '44' }}
    >
      <Box
        position='absolute'
        inset='0'
        className='hd-grid-bg hd-mask-fade'
        opacity={0.55}
        aria-hidden
      />

      <Container size='wide' position='relative'>
        <Flex
          direction={{ base: 'column', lg: 'row' }}
          align={{ base: 'stretch', lg: 'center' }}
          gap={{ base: '12', lg: '14' }}
        >
          <Box flex={{ lg: '1 1 0' }} maxW={{ lg: '580px' }} minW='0'>
            <Stack gap='6' align='flex-start'>
              <Reveal y={10} delay={0}>
                <Eyebrow>Support workspace</Eyebrow>
              </Reveal>

              <Reveal y={16} delay={stagger(1)}>
                <Heading
                  id='hero-heading'
                  as='h1'
                  fontSize={{ base: '4xl', sm: '5xl', lg: '6xl' }}
                  fontWeight='semibold'
                  letterSpacing='-0.035em'
                  lineHeight='1.04'
                  color={palette.text}
                  textWrap='balance'
                >
                  {site.tagline}
                </Heading>
              </Reveal>

              <Reveal y={14} delay={stagger(2)}>
                <Text
                  fontSize={{ base: 'md', md: 'lg' }}
                  color={palette.textSecondary}
                  lineHeight='1.7'
                  maxW='lg'
                >
                  One workspace for incoming tickets, the team working them, and the
                  conversations around them — so every customer request has a clear owner and
                  a visible next step.
                </Text>
              </Reveal>

              <Reveal y={14} delay={stagger(3)}>
                <Flex gap='3' wrap='wrap' pt='1'>
                  {signedIn ? (
                    <Button asChild {...primaryButtonProps}>
                      <RouterLink to='/dashboard'>
                        Open workspace
                        <ArrowRight size={16} aria-hidden />
                      </RouterLink>
                    </Button>
                  ) : (
                    <Button asChild {...primaryButtonProps}>
                      <RouterLink to='/sign-up'>
                        Get started
                        <ArrowRight size={16} aria-hidden />
                      </RouterLink>
                    </Button>
                  )}
                  <Button asChild {...secondaryButtonProps}>
                    <a href='#product'>
                      <Compass size={16} aria-hidden />
                      Explore the product
                    </a>
                  </Button>
                </Flex>
              </Reveal>

              <Reveal y={12} delay={stagger(4)}>
                <Stack gap='2' pt='2' as='ul' listStyleType='none' m='0' p='0'>
                  {proofPoints.map((point) => (
                    <Flex
                      as='li'
                      key={point}
                      align='center'
                      gap='2'
                      fontSize='sm'
                      color={palette.textSecondary}
                    >
                      <CheckCircle2 size={14} strokeWidth={2} color={palette.textMuted} aria-hidden />
                      {point}
                    </Flex>
                  ))}
                </Stack>
              </Reveal>
            </Stack>
          </Box>

          <Reveal flex={{ lg: '1 1 0' }} w='full' minW='0' y={20} delay={stagger(2)}>
            <ProductVisual />
          </Reveal>
        </Flex>
      </Container>
    </Box>
  )
}
