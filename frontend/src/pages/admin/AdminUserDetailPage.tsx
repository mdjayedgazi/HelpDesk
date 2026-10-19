import { Button, Flex, NativeSelect, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronLeft, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'

import { ConfirmDialog } from '../../components/ConfirmDialog.tsx'
import { FormField, FormStack, TextInput } from '../../components/FormField.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Surface } from '../../components/Surface.tsx'
import { toaster } from '../../components/Toaster.tsx'
import { ActiveStatusBadge, RoleBadge } from '../../components/badges.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { UserAvatar } from '../../components/UserAvatar.tsx'
import {
  useAdminUser,
  useUpdateUser,
  useUpdateUserRole,
  useUpdateUserStatus,
} from '../../hooks/useAdmin.ts'
import { useMe } from '../../hooks/useMe.ts'
import { errorFieldMap, errorMessage } from '../../lib/errors.ts'
import { formatDateTime, roleLabels } from '../../lib/format.ts'
import { canManageUsers } from '../../lib/roles.ts'
import { ASSIGNABLE_ROLES, type Role } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

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

export function AdminUserDetailPage() {
  const { userId } = useParams<{ userId: string }>()
  const me = useMe()
  const user = useAdminUser(userId)
  const updateUser = useUpdateUser(userId ?? '')
  const updateRole = useUpdateUserRole(userId ?? '')
  const updateStatus = useUpdateUserStatus(userId ?? '')

  const [pendingRole, setPendingRole] = useState<Role | null>(null)
  const [statusConfirmOpen, setStatusConfirmOpen] = useState(false)

  const values = useMemo<FormValues | undefined>(() => {
    if (!user.data) return undefined
    return {
      full_name: user.data.full_name,
      username: user.data.username,
      email: user.data.email,
    }
  }, [user.data])

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', username: '', email: '' },
    values,
  })

  if (user.isPending) return <LoadingState label='Loading account…' />
  if (user.isError || !user.data) {
    return (
      <ErrorState
        title='Could not load this account'
        description={user.error ? errorMessage(user.error) : undefined}
        onRetry={() => void user.refetch()}
      />
    )
  }

  const account = user.data
  const isSelf = me.data?.id === account.id
  // User management is Owner-only on the backend; an ADMIN may view the
  // directory but must not be offered role or status controls.
  const canManage = canManageUsers(me.data?.role)

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      await updateUser.mutateAsync(data)
      toaster.create({ title: 'Account updated' })
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
        title: matched ? 'Please review the highlighted fields' : 'Could not save account',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  const confirmRoleChange = async () => {
    if (!pendingRole) return
    try {
      await updateRole.mutateAsync(pendingRole)
      toaster.create({ title: `Role changed to ${roleLabels[pendingRole]}` })
      setPendingRole(null)
    } catch (error) {
      setPendingRole(null)
      toaster.create({
        title: 'Could not change role',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

  const confirmStatusChange = async () => {
    try {
      await updateStatus.mutateAsync(!account.is_active)
      toaster.create({
        title: account.is_active ? 'Account deactivated' : 'Account reactivated',
      })
      setStatusConfirmOpen(false)
    } catch (error) {
      setStatusConfirmOpen(false)
      toaster.create({
        title: 'Could not update status',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link
            to='/admin/users'
            style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}
          >
            <Flex align='center' gap='1' color={palette.textMuted} fontSize='sm'>
              <ChevronLeft size={14} aria-hidden />
              All users
            </Flex>
          </Link>
        }
        title={
          <Flex align='center' gap='3'>
            <UserAvatar name={account.full_name} size='sm' src={account.image_url} />
            <Stack gap='1'>
              <Text as='span'>{account.full_name}</Text>
              <Flex gap='2'>
                <RoleBadge role={account.role} />
                <ActiveStatusBadge isActive={account.is_active} />
              </Flex>
            </Stack>
          </Flex>
        }
        description={`@${account.username} · ${account.email}`}
      />

      <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
        <Surface p={{ base: '5', md: '6' }} gridColumn={{ lg: 'span 2' }}>
          <form onSubmit={onSubmit} noValidate>
            <FormStack>
              <FormField
                label='Full name'
                htmlFor='full_name'
                required
                error={form.formState.errors.full_name?.message}
              >
                <TextInput id='full_name' {...form.register('full_name')} />
              </FormField>
              <FormField
                label='Username'
                htmlFor='username'
                required
                error={form.formState.errors.username?.message}
              >
                <TextInput id='username' {...form.register('username')} />
              </FormField>
              <FormField
                label='Email'
                htmlFor='email'
                required
                error={form.formState.errors.email?.message}
              >
                <TextInput id='email' type='email' {...form.register('email')} />
              </FormField>
              <Flex gap='2'>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={updateUser.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save changes
                </Button>
                <Button
                  type='button'
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  disabled={!form.formState.isDirty || updateUser.isPending}
                  onClick={() => form.reset()}
                >
                  Reset
                </Button>
              </Flex>
            </FormStack>
          </form>
        </Surface>

        <Stack gap='4'>
          <Surface p='5'>
            <Stack gap='4'>
              <Flex align='center' gap='2' color={palette.text}>
                <ShieldCheck size={16} strokeWidth={1.9} aria-hidden />
                <Text fontSize='sm' fontWeight='medium'>
                  Access
                </Text>
              </Flex>

              <Stack gap='1.5'>
                <Text fontSize='xs' color={palette.textMuted}>
                  Role
                </Text>
                <NativeSelect.Root size='sm' disabled={isSelf || !canManage}>
                  <NativeSelect.Field
                    value={account.role}
                    onChange={(event) => setPendingRole(event.target.value as Role)}
                    aria-label='Change role'
                    bg={palette.surface}
                    borderColor={palette.border}
                    borderRadius='l2'
                    fontSize='sm'
                  >
                    {ASSIGNABLE_ROLES.map((value) => (
                      <option key={value} value={value}>
                        {roleLabels[value]}
                      </option>
                    ))}
                  </NativeSelect.Field>
                  <NativeSelect.Indicator color={palette.textMuted} />
                </NativeSelect.Root>
                {!canManage ? (
                  <Text fontSize='2xs' color={palette.textMuted}>
                    Only the Owner can change roles.
                  </Text>
                ) : isSelf ? (
                  <Text fontSize='2xs' color={palette.textMuted}>
                    You cannot change your own role.
                  </Text>
                ) : null}
              </Stack>

              <Stack gap='1.5'>
                <Text fontSize='xs' color={palette.textMuted}>
                  Account status
                </Text>
                <Button
                  size='sm'
                  variant='outline'
                  borderColor={palette.border}
                  justifyContent='flex-start'
                  disabled={isSelf || !canManage}
                  onClick={() => setStatusConfirmOpen(true)}
                >
                  {account.is_active ? 'Deactivate account' : 'Reactivate account'}
                </Button>
                {!canManage ? (
                  <Text fontSize='2xs' color={palette.textMuted}>
                    Only the Owner can change account status.
                  </Text>
                ) : isSelf ? (
                  <Text fontSize='2xs' color={palette.textMuted}>
                    You cannot deactivate your own account.
                  </Text>
                ) : null}
              </Stack>
            </Stack>
          </Surface>

          <Surface p='5'>
            <Stack gap='3'>
              <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                Details
              </Text>
              <DetailRow label='User ID'>
                <Text fontSize='xs' color={palette.textSecondary} fontFamily='mono'>
                  {account.id}
                </Text>
              </DetailRow>
              <DetailRow label='Created'>
                <Text fontSize='xs' color={palette.textSecondary}>
                  {formatDateTime(account.created_at)}
                </Text>
              </DetailRow>
              <DetailRow label='Updated'>
                <Text fontSize='xs' color={palette.textSecondary}>
                  {formatDateTime(account.updated_at)}
                </Text>
              </DetailRow>
            </Stack>
          </Surface>
        </Stack>
      </SimpleGrid>

      <ConfirmDialog
        open={pendingRole !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRole(null)
        }}
        title='Change role'
        description={
          pendingRole
            ? `Change this account's role from ${roleLabels[account.role]} to ${roleLabels[pendingRole]}?`
            : undefined
        }
        confirmLabel='Change role'
        loading={updateRole.isPending}
        onConfirm={() => void confirmRoleChange()}
      />

      <ConfirmDialog
        open={statusConfirmOpen}
        onOpenChange={setStatusConfirmOpen}
        title={account.is_active ? 'Deactivate account' : 'Reactivate account'}
        description={
          account.is_active
            ? 'This user will immediately lose access to HelpDesk.'
            : 'This user will be able to sign in and use HelpDesk again.'
        }
        confirmLabel={account.is_active ? 'Deactivate' : 'Reactivate'}
        loading={updateStatus.isPending}
        onConfirm={() => void confirmStatusChange()}
      />
    </>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Flex align='center' justify='space-between' gap='4'>
      <Text fontSize='xs' color={palette.textMuted} flexShrink={0}>
        {label}
      </Text>
      <Text as='span' textAlign='right' minW='0' overflow='hidden'>
        {children}
      </Text>
    </Flex>
  )
}
