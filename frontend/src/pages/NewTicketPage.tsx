import { Box, Button, Flex, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { zodResolver } from '@hookform/resolvers/zod'
import { CheckCircle2, MessageSquare, Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { PriorityBadge, StatusBadge } from '../components/badges.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { Surface } from '../components/Surface.tsx'
import { UserAvatar } from '../components/UserAvatar.tsx'
import {
  FormField,
  FormStack,
  SelectInput,
  TextAreaInput,
  TextInput,
} from '../components/FormField.tsx'
import { toaster } from '../components/Toaster.tsx'
import { useMe } from '../hooks/useMe.ts'
import { useCreateTicket } from '../hooks/useTickets.ts'
import { errorFieldMap, errorMessage } from '../lib/errors.ts'
import { impactLabels, ticketCategoryLabels } from '../lib/format.ts'
import {
  IMPACT_LEVELS,
  TICKET_CATEGORIES,
  type ImpactLevel,
  type Ticket,
  type TicketCategory,
} from '../lib/types.ts'
import { palette } from '../theme/palette.ts'

/**
 * Mirrors the backend's `PHONE_PATTERN`; the server re-validates, this is only
 * a friendlier first line of defence.
 */
const PHONE_PATTERN = /^\+?[0-9][0-9\s().-]{3,28}[0-9]$/

const schema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Give your request a short, clear title')
    .max(180, 'Title must be 180 characters or fewer'),
  category: z.enum([...TICKET_CATEGORIES] as [string, ...string[]], {
    message: 'Choose the category that fits your request',
  }),
  impact: z.enum([...IMPACT_LEVELS] as [string, ...string[]], {
    message: 'Choose how this is affecting you',
  }),
  description: z
    .string()
    .trim()
    .min(1, 'Describe what you need help with')
    .max(10000, 'Description is too long'),
  contact_phone: z
    .string()
    .trim()
    .max(32, 'Phone number is too long')
    .refine((value) => value === '' || PHONE_PATTERN.test(value), {
      message: 'Enter a valid phone number, for example +1 555 010 1234',
    }),
})

type FormValues = z.infer<typeof schema>

export function NewTicketPage() {
  const me = useMe()
  const createTicket = useCreateTicket()
  // The saved ticket, once the backend has confirmed it. Switches the page to
  // the confirmation view with the ticket number and a link to the details.
  const [created, setCreated] = useState<Ticket | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: '',
      category: '',
      impact: 'MEDIUM',
      description: '',
      contact_phone: '',
    },
  })

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      const ticket = await createTicket.mutateAsync({
        title: data.title,
        description: data.description,
        category: data.category as TicketCategory,
        impact: data.impact as ImpactLevel,
        contact_phone: data.contact_phone ? data.contact_phone : undefined,
      })
      toaster.create({
        title: `Ticket #${ticket.ticket_number} created`,
        description: 'We will keep you posted as it progresses.',
        type: 'success',
      })
      setCreated(ticket)
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
        title: matched ? 'Please review the highlighted fields' : 'Could not create ticket',
        description: matched ? undefined : errorMessage(error),
        type: 'error',
      })
    }
  })

  if (created) {
    return (
      <>
        <PageHeader title='Request received' description='Your support request has been saved.' />
        <Surface p={{ base: '5', md: '6' }} maxW='2xl'>
          <Stack gap='5' role='status' aria-live='polite'>
            <Flex align='center' gap='3' color={palette.text}>
              <CheckCircle2 size={22} strokeWidth={1.9} aria-hidden />
              <Text fontSize='lg' fontWeight='semibold'>
                Ticket #{created.ticket_number} created
              </Text>
            </Flex>
            <Text fontSize='sm' color={palette.textSecondary}>
              {created.assignee_user_id
                ? 'A support agent has been assigned and will reply on the ticket.'
                : 'Your request is in the support queue; the team has been notified and an agent will pick it up shortly.'}
            </Text>
            <Stack gap='2' fontSize='sm'>
              <Flex align='center' justify='space-between' gap='4'>
                <Text color={palette.textMuted}>Title</Text>
                <Text color={palette.text} fontWeight='medium' textAlign='end'>
                  {created.title}
                </Text>
              </Flex>
              <Flex align='center' justify='space-between' gap='4'>
                <Text color={palette.textMuted}>Status</Text>
                <StatusBadge status={created.status} />
              </Flex>
              <Flex align='center' justify='space-between' gap='4'>
                <Text color={palette.textMuted}>Priority</Text>
                <PriorityBadge priority={created.priority} />
              </Flex>
              <Flex align='center' justify='space-between' gap='4'>
                <Text color={palette.textMuted}>Category</Text>
                <Text color={palette.text}>{ticketCategoryLabels[created.category]}</Text>
              </Flex>
            </Stack>
            <Flex gap='2' wrap='wrap'>
              <Button
                asChild
                size='sm'
                bg={palette.ink}
                color={palette.textOnInk}
                _hover={{ bg: palette.inkHover }}
              >
                <Link to={`/tickets/${created.id}`}>View ticket #{created.ticket_number}</Link>
              </Button>
              <Button
                size='sm'
                variant='outline'
                borderColor={palette.border}
                onClick={() => {
                  form.reset()
                  setCreated(null)
                }}
              >
                Submit another request
              </Button>
              <Button asChild size='sm' variant='ghost' color={palette.textSecondary}>
                <Link to='/tickets'>All my tickets</Link>
              </Button>
            </Flex>
          </Stack>
        </Surface>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title='New ticket'
        description='Tell us what you need. A support agent picks it up from the queue automatically.'
      />

      <SimpleGrid columns={{ base: 1, lg: 3 }} gap='6' alignItems='start'>
        <Surface p={{ base: '5', md: '6' }} gridColumn={{ lg: 'span 2' }}>
          <form onSubmit={onSubmit} noValidate>
            <FormStack>
              <Box
                borderWidth='1px'
                borderColor={palette.borderSubtle}
                borderRadius='md'
                bg={palette.surfaceMuted}
                px='4'
                py='3'
              >
                <Text fontSize='xs' color={palette.textMuted} mb='2'>
                  Submitting as
                </Text>
                {me.data ? (
                  <Flex align='center' gap='3'>
                    <UserAvatar name={me.data.full_name} size='sm' src={me.data.image_url} />
                    <Box minW='0'>
                      <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
                        {me.data.full_name}
                      </Text>
                      <Text fontSize='xs' color={palette.textSecondary} truncate>
                        {me.data.email}
                      </Text>
                    </Box>
                  </Flex>
                ) : (
                  <Text fontSize='sm' color={palette.textSecondary}>
                    Loading your profile…
                  </Text>
                )}
                <Text fontSize='xs' color={palette.textMuted} mt='2'>
                  The ticket is filed under your signed-in account; these details come from your
                  profile and cannot be changed here.
                </Text>
              </Box>

              <FormField
                label='Title'
                htmlFor='title'
                required
                error={form.formState.errors.title?.message}
                helperText='A concise summary, for example “Unable to reset my password”.'
              >
                <TextInput
                  id='title'
                  placeholder='What do you need help with?'
                  maxLength={180}
                  {...form.register('title')}
                />
              </FormField>

              <SimpleGrid columns={{ base: 1, md: 2 }} gap='5'>
                <FormField
                  label='Category'
                  htmlFor='category'
                  required
                  error={form.formState.errors.category?.message}
                >
                  <SelectInput id='category' {...form.register('category')}>
                    <option value=''>Select a category…</option>
                    {TICKET_CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {ticketCategoryLabels[category]}
                      </option>
                    ))}
                  </SelectInput>
                </FormField>

                <FormField
                  label='Impact'
                  htmlFor='impact'
                  required
                  error={form.formState.errors.impact?.message}
                  helperText='How this is affecting you. Support uses it to set the initial priority.'
                >
                  <SelectInput id='impact' {...form.register('impact')}>
                    {IMPACT_LEVELS.map((impact) => (
                      <option key={impact} value={impact}>
                        {impactLabels[impact]}
                      </option>
                    ))}
                  </SelectInput>
                </FormField>
              </SimpleGrid>

              <FormField
                label='Description'
                htmlFor='description'
                required
                error={form.formState.errors.description?.message}
                helperText='Include steps to reproduce, what you expected, and what happened.'
              >
                <TextAreaInput
                  id='description'
                  placeholder='Describe the issue in detail…'
                  minH='48'
                  {...form.register('description')}
                />
              </FormField>

              <FormField
                label='Contact number (optional)'
                htmlFor='contact-phone'
                error={form.formState.errors.contact_phone?.message}
                helperText='Only the support team can see this number; it is never shown to anyone else.'
              >
                <TextInput
                  id='contact-phone'
                  type='tel'
                  inputMode='tel'
                  placeholder='+1 555 010 1234'
                  maxLength={32}
                  {...form.register('contact_phone')}
                />
              </FormField>

              <Flex gap='2'>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={createTicket.isPending}
                >
                  <Send size={14} aria-hidden />
                  Submit ticket
                </Button>
                <Button asChild size='sm' variant='ghost' color={palette.textSecondary}>
                  <Link to='/tickets'>Cancel</Link>
                </Button>
              </Flex>
            </FormStack>
          </form>
        </Surface>

        <Stack gap='4'>
          <Surface p='5'>
            <Stack gap='3'>
              <Flex align='center' gap='2' color={palette.text}>
                <MessageSquare size={16} strokeWidth={1.9} aria-hidden />
                <Text fontSize='sm' fontWeight='medium'>
                  What happens next?
                </Text>
              </Flex>
              <Stack gap='2.5' as='ol' ps='4'>
                <Text as='li' fontSize='xs' color={palette.textSecondary}>
                  Your impact choice sets the initial priority; the support team can adjust it
                  during triage.
                </Text>
                <Text as='li' fontSize='xs' color={palette.textSecondary}>
                  The ticket is auto-assigned to the agent with the lightest workload.
                </Text>
                <Text as='li' fontSize='xs' color={palette.textSecondary}>
                  You are notified on every status change or reply.
                </Text>
              </Stack>
            </Stack>
          </Surface>
          <Text fontSize='xs' color={palette.textMuted} px='1'>
            You can reply on the ticket once it has been created. Include the contact number only if
            you are comfortable being called.
          </Text>
        </Stack>
      </SimpleGrid>
    </>
  )
}
