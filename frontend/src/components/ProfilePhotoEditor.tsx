import { useUser } from '@clerk/react'
import { Button, Flex, Text } from '@chakra-ui/react'
import { Camera } from 'lucide-react'
import { useRef, useState } from 'react'

import { useMe } from '../hooks/useMe.ts'
import { useSyncAvatar } from '../hooks/useProfile.ts'
import { errorMessage } from '../lib/errors.ts'
import { palette } from '../theme/palette.ts'
import { toaster } from './Toaster.tsx'
import { UserAvatar } from './UserAvatar.tsx'

// Formats Clerk accepts for a profile image. Kept in sync with the file picker
// `accept` list below.
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const ACCEPT_ATTR = ACCEPTED_TYPES.join(',')
const MAX_BYTES = 5 * 1024 * 1024 // 5 MiB

/**
 * Lets the signed-in user change their own profile photo.
 *
 * Clerk is the source of truth: the image is uploaded to Clerk
 * (`user.setProfileImage`), then the backend is asked to re-read the verified
 * image URL (`POST /users/me/avatar`). An optimistic local preview shows the
 * chosen file immediately. A client can only ever change *its own* photo — the
 * Clerk method operates on the current session and there is no user id in the
 * request.
 */
export function ProfilePhotoEditor({ name }: { name: string }) {
  const { user } = useUser()
  const me = useMe()
  const syncAvatar = useSyncAvatar()
  const inputRef = useRef<HTMLInputElement>(null)
  const objectUrlRef = useRef<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  // Prefer the freshest source: local preview -> live Clerk URL -> cached value.
  const src = preview ?? user?.imageUrl ?? me.data?.image_url ?? null

  function releasePreview() {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setPreview(null)
  }

  function openPicker() {
    if (uploading) return
    inputRef.current?.click()
  }

  async function onFile(file: File) {
    if (!user) {
      toaster.create({
        title: 'You need to be signed in to change your photo',
        type: 'error',
      })
      return
    }
    if (!ACCEPTED_TYPES.includes(file.type)) {
      toaster.create({
        title: 'Unsupported image type',
        description: 'Choose a PNG, JPEG, WebP or GIF image.',
        type: 'error',
      })
      return
    }
    if (file.size > MAX_BYTES) {
      toaster.create({
        title: 'Image is too large',
        description: 'Choose an image smaller than 5 MB.',
        type: 'error',
      })
      return
    }

    releasePreview()
    const url = URL.createObjectURL(file)
    objectUrlRef.current = url
    setPreview(url)
    setUploading(true)
    try {
      await user.setProfileImage({ file })
      // Re-read the verified URL from Clerk (server-side) so other users see it.
      await syncAvatar.mutateAsync()
      releasePreview()
      toaster.create({ title: 'Profile photo updated' })
    } catch (error) {
      releasePreview()
      toaster.create({
        title: 'Could not update your photo',
        description: errorMessage(error),
        type: 'error',
      })
    } finally {
      setUploading(false)
    }
  }

  return (
    <Flex direction='column' align='center' gap='3'>
      <UserAvatar name={name} src={src} size='xl' />
      <input
        ref={inputRef}
        type='file'
        accept={ACCEPT_ATTR}
        hidden
        aria-label='Choose a profile photo'
        onChange={(event) => {
          const file = event.target.files?.[0]
          // Reset so choosing the same file again still fires a change event.
          event.target.value = ''
          if (file) void onFile(file)
        }}
      />
      <Button
        type='button'
        size='sm'
        variant='outline'
        onClick={openPicker}
        loading={uploading}
        disabled={uploading || !user}
        aria-label='Change profile photo'
        borderColor={palette.border}
        color={palette.text}
        _hover={{ bg: palette.hover }}
      >
        <Camera size={15} aria-hidden />
        Change photo
      </Button>
      <Text fontSize='2xs' color={palette.textMuted} textAlign='center'>
        PNG, JPEG, WebP or GIF · up to 5 MB
      </Text>
    </Flex>
  )
}
