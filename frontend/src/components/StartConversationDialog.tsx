import { Button, Dialog, Portal, Stack, Text } from '@chakra-ui/react'
import { useState } from 'react'

import { FormField, TextInput } from './FormField.tsx'
import { StaffConversationPicker } from './StaffConversationPicker.tsx'
import { toaster } from './Toaster.tsx'
import { useStartStaffConversation } from '../hooks/useStaffMessages.ts'
import { errorMessage } from '../lib/errors.ts'
import type { StaffConversation } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'

/**
 * Start (or open) a 1:1 conversation with any eligible teammate.
 *
 * Shared by the agent/admin workspace and the Owner inbox so every staff role
 * can initiate a conversation with any other. The picker is backed by the
 * staff-only directory; the backend validates the recipient and returns the
 * existing thread if the pair already has one.
 */
export function StartConversationDialog({
  open,
  onOpenChange,
  onStarted,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarted: (conversation: StaffConversation) => void
}) {
  const start = useStartStaffConversation()
  const [recipientId, setRecipientId] = useState('')
  const [subject, setSubject] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!recipientId) {
      toaster.create({ title: 'Choose a teammate to message', type: 'error' })
      return
    }
    try {
      const conversation = await start.mutateAsync({
        recipient_user_id: recipientId,
        subject: subject.trim() || undefined,
      })
      toaster.create({
        title: 'Conversation ready',
        description: 'You can start messaging your teammate now.',
      })
      onOpenChange(false)
      setRecipientId('')
      setSubject('')
      onStarted(conversation)
    } catch (error) {
      toaster.create({
        title: 'Could not start the conversation',
        description: errorMessage(error),
        type: 'error',
      })
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(details) => onOpenChange(details.open)}>
      <Portal>
        <Dialog.Backdrop bg={palette.overlay} />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='lg'
            boxShadow={palette.shadowLg}
          >
            <form onSubmit={submit} noValidate>
              <Dialog.Header px='6' pt='6' pb='2'>
                <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                  New message
                </Dialog.Title>
                <Text fontSize='xs' color={palette.textMuted} pt='2'>
                  Pick any teammate. If you already have a thread together, it opens instead of
                  creating a duplicate.
                </Text>
              </Dialog.Header>
              <Dialog.Body px='6' py='4'>
                <Stack gap='4'>
                  <FormField label='Teammate' htmlFor='conversation-recipient' required>
                    <StaffConversationPicker value={recipientId} onChange={setRecipientId} />
                  </FormField>
                  <FormField
                    label='Subject (optional)'
                    htmlFor='conversation-subject'
                    helperText='A short line so your teammate can triage, for example “Refund approval request”.'
                  >
                    <TextInput
                      id='conversation-subject'
                      maxLength={180}
                      value={subject}
                      onChange={(event) => setSubject(event.target.value)}
                      placeholder='What is this about?'
                    />
                  </FormField>
                </Stack>
              </Dialog.Body>
              <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
                <Button
                  size='sm'
                  variant='ghost'
                  color={palette.textSecondary}
                  onClick={() => onOpenChange(false)}
                  disabled={start.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type='submit'
                  size='sm'
                  bg={palette.ink}
                  color={palette.textOnInk}
                  _hover={{ bg: palette.inkHover }}
                  loading={start.isPending}
                  disabled={!recipientId}
                >
                  Start conversation
                </Button>
              </Dialog.Footer>
            </form>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
