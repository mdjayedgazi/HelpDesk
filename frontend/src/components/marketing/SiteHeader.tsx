import { Box, Button, Flex, IconButton, Link, Stack } from '@chakra-ui/react'
import { useAuth } from '@clerk/react'
import { Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

import { navHeight } from '../../theme/layout.ts'
import { palette } from '../../theme/palette.ts'
import { Container } from '../Container.tsx'
import { Logo } from '../Logo.tsx'
import { ThemeToggle } from '../ThemeToggle.tsx'

const NAV_LINKS = [
  { label: 'Product', href: '#product' },
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Security', href: '#security' },
] as const

const primaryButtonProps = {
  size: 'sm',
  bg: palette.ink,
  color: palette.textOnInk,
  _hover: { bg: palette.inkHover },
} as const

const secondaryButtonProps = {
  size: 'sm',
  variant: 'ghost',
  color: palette.textSecondary,
  _hover: { bg: palette.hover, color: palette.text },
} as const

function SectionLink({ href, label, onClick }: { href: string; label: string; onClick?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onClick}
      px='3'
      py='2'
      borderRadius='l2'
      fontSize='sm'
      fontWeight='medium'
      color={palette.textSecondary}
      transition='background 0.16s ease, color 0.16s ease'
      _hover={{ bg: palette.hover, color: palette.text, textDecoration: 'none' }}
    >
      {label}
    </Link>
  )
}

function MobileNav({ signedIn, onNavigate }: { signedIn: boolean; onNavigate: () => void }) {
  return (
    <Box
      id='marketing-mobile-nav'
      display={{ base: 'block', lg: 'none' }}
      borderTopWidth='1px'
      borderColor={palette.border}
      bg={palette.surface}
      className='hd-menu-in'
    >
      <Container size='wide'>
        <Stack gap='1' py='4'>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={onNavigate}
              px='3'
              py='2.5'
              borderRadius='l2'
              fontSize='sm'
              fontWeight='medium'
              color={palette.text}
              _hover={{ bg: palette.hover, textDecoration: 'none' }}
            >
              {link.label}
            </Link>
          ))}
        </Stack>
        <Stack gap='2' pb='5' pt='2' borderTopWidth='1px' borderColor={palette.borderSubtle}>
          {signedIn ? (
            <Button asChild {...primaryButtonProps} width='full'>
              <RouterLink to='/dashboard' onClick={onNavigate}>
                Open workspace
              </RouterLink>
            </Button>
          ) : (
            <>
              <Button asChild {...primaryButtonProps} width='full'>
                <RouterLink to='/sign-up' onClick={onNavigate}>
                  Get started
                </RouterLink>
              </Button>
              <Button asChild {...secondaryButtonProps} width='full' borderWidth='1px' borderColor={palette.border}>
                <RouterLink to='/sign-in' onClick={onNavigate}>
                  Sign in
                </RouterLink>
              </Button>
            </>
          )}
        </Stack>
      </Container>
    </Box>
  )
}

/**
 * Sticky marketing navigation.
 *
 * Rendered only on the public homepage, so its anchor links always resolve to a
 * section that exists on the current page.
 */
export function SiteHeader() {
  const { isLoaded, isSignedIn } = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const signedIn = isLoaded && isSignedIn

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <Box
      as='header'
      position='sticky'
      top='0'
      zIndex='40'
      bg={palette.glass}
      backdropFilter='blur(14px)'
      borderBottomWidth='1px'
      borderColor={palette.border}
    >
      <Container size='wide'>
        <Flex align='center' justify='space-between' gap='4' height={navHeight}>
          <Link
            asChild
            _hover={{ textDecoration: 'none' }}
            aria-label={`${'HelpDesk'} home`}
          >
            <RouterLink to='/'>
              <Logo />
            </RouterLink>
          </Link>

          <Flex as='nav' aria-label='Primary' display={{ base: 'none', lg: 'flex' }} align='center' gap='0.5'>
            {NAV_LINKS.map((link) => (
              <SectionLink key={link.href} href={link.href} label={link.label} />
            ))}
          </Flex>

          <Flex align='center' gap='2'>
            <ThemeToggle />
            {signedIn ? (
              <Button
                asChild
                {...primaryButtonProps}
                display={{ base: 'none', sm: 'inline-flex' }}
              >
                <RouterLink to='/dashboard'>Open workspace</RouterLink>
              </Button>
            ) : (
              <>
                <Button
                  asChild
                  {...secondaryButtonProps}
                  display={{ base: 'none', sm: 'inline-flex' }}
                >
                  <RouterLink to='/sign-in'>Sign in</RouterLink>
                </Button>
                <Button
                  asChild
                  {...primaryButtonProps}
                  display={{ base: 'none', sm: 'inline-flex' }}
                >
                  <RouterLink to='/sign-up'>Get started</RouterLink>
                </Button>
              </>
            )}
            <IconButton
              aria-label={open ? 'Close menu' : 'Open menu'}
              aria-expanded={open}
              aria-controls='marketing-mobile-nav'
              aria-haspopup='true'
              variant='ghost'
              size='sm'
              color={palette.textSecondary}
              borderWidth='1px'
              borderColor={palette.border}
              borderRadius='l2'
              _hover={{ bg: palette.hover, color: palette.text }}
              display={{ base: 'inline-flex', lg: 'none' }}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? <X size={16} strokeWidth={1.9} aria-hidden /> : <Menu size={16} strokeWidth={1.9} aria-hidden />}
            </IconButton>
          </Flex>
        </Flex>
      </Container>

      {open ? <MobileNav signedIn={Boolean(signedIn)} onNavigate={() => setOpen(false)} /> : null}
    </Box>
  )
}
