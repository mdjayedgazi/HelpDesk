import { Avatar } from '@chakra-ui/react'

import { initials } from '../lib/format.ts'
import { palette } from '../theme/palette.ts'

/**
 * A user avatar with a graceful fallback.
 *
 * When `src` is provided (a Clerk-hosted image URL synced into the profile) the
 * photo is shown; otherwise — or if the image fails to load — the user's
 * initials are rendered. This is used consistently in the navbar, account menu,
 * profile page, staff tables, comment threads and messaging views.
 */
export function UserAvatar({
  name,
  src,
  size = 'sm',
  tone = 'neutral',
}: {
  name: string
  src?: string | null
  size?: '2xs' | 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  tone?: 'neutral' | 'ink'
}) {
  return (
    <Avatar.Root
      size={size}
      bg={tone === 'ink' ? palette.ink : palette.inset}
      color={tone === 'ink' ? palette.textOnInk : palette.text}
      borderWidth='1px'
      borderColor={palette.border}
    >
      {src ? <Avatar.Image src={src} alt={name} /> : null}
      <Avatar.Fallback name={name} fontSize='2xs' fontWeight='medium'>
        {initials(name)}
      </Avatar.Fallback>
    </Avatar.Root>
  )
}
