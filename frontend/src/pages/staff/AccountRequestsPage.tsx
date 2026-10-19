import { Button, Dialog, Flex, NativeSelect, Portal, Stack, Table, Text } from '@chakra-ui/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { ShieldQuestion } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import { EscalationStatusBadge } from '../../components/badges.tsx'
import { FormField, FormStack, SelectInput, TextAreaInput } from '../../components/FormField.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { EmptyState, ErrorState, TableSkeleton } from '../../components/StateViews.tsx'
import { Surface } from '../../components/Surface.tsx'
import { toaster } from '../../components/Toaster.tsx'
import { useAccountRequests, useCreateAccountRequest } from '../../hooks/useAccountRequests.ts'
import { useAdminUsers } from '../../hooks/useAdmin.ts'
import { useMe } from '../../hooks/useMe.ts'
import { useTickets } from '../../hooks/useTickets.ts'
import { useUserDirectory } from '../../hooks/useUserDirectory.ts'
import { errorFieldMap, errorMessage } from '../../lib/errors.ts'
import {
  escalationCategoryLabels,
  escalationStatusLabels,
  formatRelative,
  ticketRef,
} from '../../lib/format.ts'
import { isAdmin } from '../../lib/roles.ts'
import {
  ESCALATION_CATEGORIES,
  ESCALATION_STATUSES,
  type EscalationStatus,
} from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

export function AccountRequestsPage() {
  const me = useMe()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const directory = useUserDirectory()

  const role = me.data?.role
  const admin = isAdmin(role)
  const canCreate = role === 'agent' || role === 'admin'

  const [status, setStatus] = useState<EscalationStatus | ''>('')
  const [mine, setMine] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)

  const params = useMemo(
    () => ({
      status: status || undefined,
      mine: admin && mine ? true : undefined,
      limit: 100,
    }),
    [status, mine, admin],
  )

  const requests = useAccountRequests(params)
  const items = requests.data ?? []
  const prefilledTicket = searchParams.get('ticket') ?? undefined

  return (
    <>
      <PageHeader
        title='Account requests'
        description='Structured requests for privileged account actions, reviewed by administrators.'
        actions={
          canCreate ? (
            <Button
              size='sm'
              bg={palette.ink}
              color={palette.textOnInk}
              _hover={{ bg: palette.inkHover }}
              onClick={() => setCreateOpen(true)}
            >
              <ShieldQuestion size={14} aria-hidden />
              New request
            </Button>
          ) : null
        }
      />

      <Flex mb='5' wrap='wrap' gap='4' align='center'>
        <NativeSelect.Root size='sm' maxW='13rem'>
          <NativeSelect.Field
            value={status}
            onChange={(event) => setStatus(event.target.value as EscalationStatus | '')}
            aria-label='Filter by status'
            bg={palette.surface}
            borderColor={palette.border}
            borderRadius='l2'
            fontSize='sm'
          >
            <option value=''>All statuses</option>
            {ESCALATION_STATUSES.map((value) => (
              <option key={value} value={value}>
                {escalationStatusLabels[value]}
              </option>
            ))}
          </NativeSelect.Field>
          <NativeSelect.Indicator color={palette.textMuted} />
        </NativeSelect.Root>

        {admin ? (
          <Button
            size='sm'
            variant={mine ? 'solid' : 'outline'}
            borderColor={palette.border}
            bg={mine ? palette.ink : undefined}
            color={mine ? palette.textOnInk : undefined}
            _hover={{ bg: mine ? palette.inkHover : palette.hover }}
            onClick={() => setMine((value) => !value)}
            aria-pressed={mine}
          >
            My requests only
          </Button>
        ) : null}
      </Flex>

      {requests.isPending ? (
        <Surface overflow='hidden'>
          <TableSkeleton rows={6} columns={5} />
        </Surface>
      ) : requests.isError ? (
        <ErrorState
          title='Could not load account requests'
          description={errorMessage(requests.error)}
          onRetry={() => void requests.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={ShieldQuestion}
          title={
            admin && !mine && !status
              ? 'No account requests yet'
              : 'No requests match these filters'
          }
          description={
            canCreate
              ? 'Open a request when a customer needs an account action you cannot perform yourself.'
              : undefined
          }
          action={
            canCreate ? (
              <Button
                size='sm'
                variant='outline'
                borderColor={palette.border}
                onClick={() => setCreateOpen(true)}
              >
                New request
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Surface overflow='hidden'>
          <Table.ScrollArea>
            <Table.Root size='sm' variant='line' interactive>
              <Table.Header>
                <Table.Row bg={palette.surface}>
                  <Table.ColumnHeader color={palette.textMuted} fontSize='xs' fontWeight='medium'>
                    Request
                  </Table.ColumnHeader>
                  <Table.ColumnHeader
                    color={palette.textMuted}
                    fontSize='xs'
                    fontWeight='medium'
                    display={{ base: 'none', md: 'table-cell' }}
                  >
                    Status
                  </Table.ColumnHeader>
                  <Table.ColumnHeader
                    color={palette.textMuted}
                    fontSize='xs'
                    fontWeight='medium'
                    display={{ base: 'none', lg: 'table-cell' }}
                  >
                    Account
                  </Table.ColumnHeader>
                  <Table.ColumnHeader
                    color={palette.textMuted}
                    fontSize='xs'
                    fontWeight='medium'
                    display={{ base: 'none', lg: 'table-cell' }}
                  >
                    Requested by
                  </Table.ColumnHeader>
                  <Table.ColumnHeader
                    color={palette.textMuted}
                    fontSize='xs'
                    fontWeight='medium'
                    textAlign='right'
                  >
                    Updated
                  </Table.ColumnHeader>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {items.map((request) => (
                  <Table.Row
                    key={request.id}
                    cursor='pointer'
                    transition='background 0.16s ease'
                    _hover={{ bg: palette.hover }}
                  >
                    <Table.Cell py='3.5' maxW='0'>
                      <Stack gap='1' minW='0'>
                        <Link
                          to={`/account-requests/${request.id}`}
                          style={{ textDecoration: 'none' }}
                        >
                          <Text
                            fontSize='sm'
                            fontWeight='medium'
                            color={palette.text}
                            truncate
                            _hover={{ textDecoration: 'underline' }}
                          >
                            {escalationCategoryLabels[request.category]}
                          </Text>
                        </Link>
                        <Flex align='center' gap='2' wrap='wrap'>
                          <Text
                            fontSize='2xs'
                            color={palette.textMuted}
                            fontVariantNumeric='tabular-nums'
                          >
                            {request.id.slice(0, 8)}
                          </Text>
                          {request.ticket_id ? (
                            <Link
                              to={`/tickets/${request.ticket_id}`}
                              style={{ textDecoration: 'underline' }}
                            >
                              <Text fontSize='2xs' color={palette.textMuted}>
                                Related ticket
                              </Text>
                            </Link>
                          ) : null}
                        </Flex>
                        <Flex display={{ base: 'flex', md: 'none' }}>
                          <EscalationStatusBadge status={request.status} />
                        </Flex>
                      </Stack>
                    </Table.Cell>
                    <Table.Cell display={{ base: 'none', md: 'table-cell' }}>
                      <EscalationStatusBadge status={request.status} />
                    </Table.Cell>
                    <Table.Cell
                      display={{ base: 'none', lg: 'table-cell' }}
                      fontSize='sm'
                      color={palette.textSecondary}
                    >
                      {request.target_full_name_snapshot}
                    </Table.Cell>
                    <Table.Cell
                      display={{ base: 'none', lg: 'table-cell' }}
                      fontSize='sm'
                      color={palette.textSecondary}
                      whiteSpace='nowrap'
                    >
                      {directory.label(request.created_by_user_id)}
                    </Table.Cell>
                    <Table.Cell
                      textAlign='right'
                      fontSize='xs'
                      color={palette.textMuted}
                      whiteSpace='nowrap'
                    >
                      {formatRelative(request.updated_at)}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table.Root>
          </Table.ScrollArea>
        </Surface>
      )}

      {canCreate ? (
        <CreateRequestDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          prefilledTicketId={prefilledTicket}
          onCreated={(id) => void navigate(`/account-requests/${id}`)}
        />
      ) : null}
    </>
  )
}

const createSchema = z.object({
  category: z.enum([...ESCALATION_CATEGORIES] as [string, ...string[]], {
    message: 'Choose what kind of account action is needed',
  }),
  justification: z
    .string()
    .trim()
    .min(1, 'Explain why this account action is needed')
    .max(4000, 'Keep the justification under 4000 characters'),
  internal_details: z
    .string()
    .trim()
    .max(4000, 'Keep internal details under 4000 characters')
    .optional(),
  ticket_id: z.string().optional(),
  target_user_id: z.string().optional(),
})

type CreateValues = z.infer<typeof createSchema>

function CreateRequestDialog({
  open,
  onOpenChange,
  prefilledTicketId,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  prefilledTicketId?: string
  onCreated: (id: string) => void
}) {
  const me = useMe()
  const role = me.data?.role
  const admin = isAdmin(role)

  const tickets = useTickets({ limit: 100 })
  const users = useAdminUsers({ limit: 100 }, admin)
  const create = useCreateAccountRequest()

  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      category: '',
      justification: '',
      internal_details: '',
      ticket_id: prefilledTicketId ?? '',
      target_user_id: '',
    },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const request = await create.mutateAsync({
        category: values.category as (typeof ESCALATION_CATEGORIES)[number],
        justification: values.justification,
        internal_details: values.internal_details || undefined,
        ticket_id: values.ticket_id || undefined,
        target_user_id: admin && values.target_user_id ? values.target_user_id : undefined,
      })
      toaster.create({
        title: 'Request submitted',
        description: 'An administrator will review it shortly.',
      })
      onOpenChange(false)
      form.reset()
      onCreated(request.id)
    } catch (error) {
      const fields = errorFieldMap(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in createSchema.shape) {
          form.setError(field as keyof CreateValues, { message })
          matched = true
        }
      }
      toaster.create({
        title: matched ? 'Please review the highlighted fields' : 'Could not submit the request',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  return (
    <Dialog.Root open={open} onOpenChange={(details) => onOpenChange(details.open)}>
      <Portal>
        <Dialog.Backdrop bg='rgba(17,17,17,0.32)' />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='xl'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <form onSubmit={onSubmit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  New account request
                </Dialog.Title>
                <Text fontSize='xs' color={palette.textMuted} pt='2'>
                  This asks an administrator for a privileged account action. The target account is
                  taken from the selected ticket, never typed in by hand.
                </Text>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <FormStack>
                  <FormField
                    label='Category'
                    htmlFor='request-category'
                    required
                    error={form.formState.errors.category?.message}
                  >
                    <SelectInput id='request-category' {...form.register('category')}>
                      <option value=''>Select a category…</option>
                      {ESCALATION_CATEGORIES.map((category) => (
                        <option key={category} value={category}>
                          {escalationCategoryLabels[category]}
                        </option>
                      ))}
                    </SelectInput>
                  </FormField>

                  <FormField
                    label='Related ticket'
                    htmlFor='request-ticket'
                    required={role === 'agent'}
                    error={form.formState.errors.ticket_id?.message}
                    helperText={
                      role === 'agent'
                        ? 'Required: the request targets the ticket requester.'
                        : 'Optional for administrators: leave empty when the request is not ticket-bound.'
                    }
                  >
                    <SelectInput id='request-ticket' {...form.register('ticket_id')}>
                      <option value=''>No related ticket</option>
                      {(tickets.data ?? []).map((ticket) => (
                        <option key={ticket.id} value={ticket.id}>
                          {ticketRef(ticket.ticket_number)} — {ticket.title}
                        </option>
                      ))}
                    </SelectInput>
                  </FormField>

                  {admin ? (
                    <FormField
                      label='Target account (administrators only)'
                      htmlFor='request-target'
                      error={form.formState.errors.target_user_id?.message}
                      helperText='Optional. Must match the ticket requester when a ticket is selected.'
                    >
                      <SelectInput id='request-target' {...form.register('target_user_id')}>
                        <option value=''>Use the ticket requester</option>
                        {(users.data ?? []).map((user) => (
                          <option key={user.id} value={user.id}>
                            {user.full_name} ({user.email})
                          </option>
                        ))}
                      </SelectInput>
                    </FormField>
                  ) : null}

                  <FormField
                    label='Justification'
                    htmlFor='request-justification'
                    required
                    error={form.formState.errors.justification?.message}
                    helperText='What happened and why the customer cannot be helped without this action.'
                  >
                    <TextAreaInput
                      id='request-justification'
                      minH='28'
                      maxLength={4000}
                      {...form.register('justification')}
                    />
                  </FormField>

                  <FormField
                    label='Internal details (optional)'
                    htmlFor='request-details'
                    error={form.formState.errors.internal_details?.message}
                    helperText='Only reviewers can see this. Never include passwords or tokens.'
                  >
                    <TextAreaInput
                      id='request-details'
                      minH='20'
                      maxLength={4000}
                      {...form.register('internal_details')}
                    />
                  </FormField>
                </FormStack>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={create.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={create.isPending}
                >
                  Submit request
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
