import { Button, Flex, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { PageHeader } from '../components/PageHeader.tsx'
import { ProfilePhotoEditor } from '../components/ProfilePhotoEditor.tsx'
import { Surface } from '../components/Surface.tsx'
import { FormField, FormStack, TextInput } from '../components/FormField.tsx'
import { ActiveStatusBadge, RoleBadge } from '../components/badges.tsx'
import { LoadingState, ErrorState } from '../components/StateViews.tsx'
import { toaster } from '../components/Toaster.tsx'
import { useMe } from '../hooks/useMe.ts'
import { useUpdateProfile } from '../hooks/useProfile.ts'
import { errorFieldMap, errorMessage } from '../lib/errors.ts'
import { formatDate } from '../lib/format.ts'
import { palette } from '../theme/palette.ts'

const schema = z.object({
  full_name: z
    .string()
    .trim()
    .min(2, 'Name must be at least 2 characters')
    .max(120, 'Name must be 120 characters or fewer'),
  username: z
    .string()
    .trim()
    .min(2, 'Username must be at least 2 characters')
    .max(90, 'Username must be 90 characters or fewer')
    .regex(/^[A-Za-z0-9_.-]+$/, 'Use letters, numbers, dots, dashes or underscores'),
  email: z.string().trim().min(1, 'Email is required').email('Enter a valid email address'),
})

type FormValues = z.infer<typeof schema>

export function ProfilePage() {
  const me = useMe()
  const updateProfile = useUpdateProfile()

  const values = useMemo<FormValues | undefined>(() => {
    if (!me.data) return undefined
    return {
      full_name: me.data.full_name,
      username: me.data.username,
      email: me.data.email,
    }
  }, [me.data])

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', username: '', email: '' },
    values,
  })

  if (me.isPending) return <LoadingState label='Loading profile…' />
  if (me.isError || !me.data) {
    return (
      <ErrorState
        title='Could not load your profile'
        description={me.error ? errorMessage(me.error) : undefined}
        onRetry={() => void me.refetch()}
      />
    )
  }

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      await updateProfile.mutateAsync(data)
      toaster.create({ title: 'Profile updated' })
      form.reset(data)
    } catch (error) {
      const fields = errorFieldMap(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in schema.shape) {
          form.setError(field as keyof FormValues, { message })
          matched = true
        }
      }
      toaster.create({
        title: matched ? 'Please review the highlighted fields' : 'Could not save profile',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  const profile = me.data

  return (
    <>
      <PageHeader
        title='Profile'
        description='Manage how your name and contact details appear across HelpDesk.'
      />

      <SimpleGrid columns={{ base: 1, lg: 2 }} gap='6' alignItems='start'>
        <Surface p={{ base: '5', md: '6' }}>
          <form onSubmit={onSubmit} noValidate>
            <FormStack>
              <FormField
                label='Full name'
                htmlFor='full_name'
                required
                error={form.formState.errors.full_name?.message}
              >
                <TextInput id='full_name' autoComplete='name' {...form.register('full_name')} />
              </FormField>

              <FormField
                label='Username'
                htmlFor='username'
                required
                error={form.formState.errors.username?.message}
                helperText='Used to reference your account internally.'
              >
                <TextInput id='username' autoComplete='username' {...form.register('username')} />
              </FormField>

              <FormField
                label='Email'
                htmlFor='email'
                required
                error={form.formState.errors.email?.message}
                helperText='Your sign-in email is managed by Clerk. Updating it here changes your HelpDesk contact email.'
              >
                <TextInput
                  id='email'
                  type='email'
                  autoComplete='email'
                  {...form.register('email')}
                />
              </FormField>

              <Flex gap='2' pt='1'>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={updateProfile.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save changes
                </Button>
                <Button
                  type='button'
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  disabled={!form.formState.isDirty || updateProfile.isPending}
                  onClick={() => form.reset()}
                >
                  Reset
                </Button>
              </Flex>
            </FormStack>
          </form>
        </Surface>

        <Stack gap='4'>
          <Surface p={{ base: '5', md: '6' }}>
            <Stack gap='4' align='center'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                Profile photo
              </Text>
              <ProfilePhotoEditor name={profile.full_name} />
            </Stack>
          </Surface>
          <Surface p={{ base: '5', md: '6' }}>
            <Stack gap='4'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                Account
              </Text>
              <Stack gap='3'>
                <DetailRow label='Role'>
                  <RoleBadge role={profile.role} />
                </DetailRow>
                <DetailRow label='Status'>
                  <ActiveStatusBadge isActive={profile.is_active} />
                </DetailRow>
                <DetailRow label='Member since'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {formatDate(profile.created_at)}
                  </Text>
                </DetailRow>
                <DetailRow label='Last updated'>
                  <Text fontSize='sm' color={palette.textSecondary}>
                    {formatDate(profile.updated_at)}
                  </Text>
                </DetailRow>
              </Stack>
            </Stack>
          </Surface>
          <Text fontSize='xs' color={palette.textMuted} px='1'>
            Your role is assigned by an administrator and cannot be changed from your profile.
          </Text>
        </Stack>
      </SimpleGrid>
    </>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Flex align='center' justify='space-between' gap='4'>
      <Text fontSize='sm' color={palette.textMuted}>
        {label}
      </Text>
      {children}
    </Flex>
  )
}
