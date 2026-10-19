import { Box, Flex, Link, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { useAuth } from '@clerk/react'
import { Link as RouterLink } from 'react-router-dom'

import { site } from '../../lib/site.ts'
import { palette } from '../../theme/palette.ts'
import { Container } from '../Container.tsx'
import { Logo } from '../Logo.tsx'

const exploreLinks = [
  { label: 'Product', href: '/#product' },
  { label: 'Features', href: '/#features' },
  { label: 'How it works', href: '/#how-it-works' },
  { label: 'Security', href: '/#security' },
] as const

function FooterHeading({ children }: { children: React.ReactNode }) {
  return (
    <Text
      fontSize='2xs'
      fontWeight='semibold'
      letterSpacing='0.08em'
      textTransform='uppercase'
      color={palette.textFaint}
    >
      {children}
    </Text>
  )
}

function FooterLink({ to, children }: { to: string; children: React.ReactNode }) {
  const shared = {
    fontSize: 'sm',
    color: palette.textSecondary,
    width: 'fit-content',
    transition: 'color 0.16s ease',
    _hover: { color: palette.text, textDecoration: 'none' },
  } as const

  if (to.startsWith('/#')) {
    return (
      <Link href={to} {...shared}>
        {children}
      </Link>
    )
  }

  return (
    <Link asChild {...shared}>
      <RouterLink to={to}>{children}</RouterLink>
    </Link>
  )
}

/**
 * Public site footer, reused across the marketing surface.
 *
 * Anchors use `/#section` so they resolve correctly even when the footer is
 * rendered from a route other than the homepage.
 */
export function SiteFooter() {
  const year = new Date().getFullYear()
  const { isLoaded, isSignedIn } = useAuth()
  const signedIn = isLoaded && isSignedIn

  return (
    <Box as='footer' borderTopWidth='1px' borderColor={palette.border} bg={palette.surface}>
      <Container size='wide'>
        <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} gap={{ base: '10', md: '12' }} py={{ base: '12', md: '16' }}>
          <Stack gap='4' gridColumn={{ lg: 'span 2' }}>
            <RouterLink to='/' style={{ textDecoration: 'none', width: 'fit-content' }} aria-label='HelpDesk home'>
              <Logo />
            </RouterLink>
            <Text fontSize='sm' color={palette.textSecondary} maxW='xs' lineHeight='1.7'>
              {site.description}
            </Text>
          </Stack>

          <Stack gap='3'>
            <FooterHeading>Explore</FooterHeading>
            {exploreLinks.map((link) => (
              <FooterLink key={link.href} to={link.href}>
                {link.label}
              </FooterLink>
            ))}
          </Stack>

          <Stack gap='3'>
            <FooterHeading>Get started</FooterHeading>
            {signedIn ? (
              <FooterLink to='/dashboard'>Open workspace</FooterLink>
            ) : (
              <>
                <FooterLink to='/sign-in'>Sign in</FooterLink>
                <FooterLink to='/sign-up'>Create an account</FooterLink>
              </>
            )}
          </Stack>
        </SimpleGrid>

        <Flex
          borderTopWidth='1px'
          borderColor={palette.borderSubtle}
          py={{ base: '6', md: '7' }}
          gap={{ base: '2', md: '6' }}
          direction={{ base: 'column', md: 'row' }}
          align={{ base: 'flex-start', md: 'center' }}
          justify='space-between'
        >
          <Text fontSize='xs' color={palette.textMuted}>
            © {year} HelpDesk. All rights reserved.
          </Text>
          <Text fontSize='xs' color={palette.textMuted}>
            Designed &amp; built by{' '}
            <Text as='span' color={palette.text} fontWeight='medium'>
              {site.author}
            </Text>
          </Text>
        </Flex>
      </Container>
    </Box>
  )
}
