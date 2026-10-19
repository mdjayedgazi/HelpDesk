import { Button, Dialog, Portal, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
  onConfirm: () => void
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  loading = false,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(details) => onOpenChange(details.open)}
      role='alertdialog'
    >
      <Portal>
        <Dialog.Backdrop bg='rgba(17,17,17,0.32)' />
        <Dialog.Positioner>
          <Dialog.Content
            bg={palette.surface}
            borderWidth='1px'
            borderColor={palette.border}
            borderRadius='l3'
            maxW='md'
            boxShadow='0 24px 60px -24px rgba(0,0,0,0.28)'
          >
            <Dialog.Header px='6' pt='6' pb='2'>
              <Dialog.Title fontSize='md' fontWeight='medium' color={palette.text}>
                {title}
              </Dialog.Title>
            </Dialog.Header>
            {description ? (
              <Dialog.Body px='6' pb='4'>
                <Text fontSize='sm' color={palette.textSecondary}>
                  {description}
                </Text>
              </Dialog.Body>
            ) : (
              <Dialog.Body py='2' />
            )}
            <Dialog.Footer px='6' pb='6' pt='2' gap='2'>
              <Button
                variant='ghost'
                size='sm'
                color={palette.textSecondary}
                onClick={() => onOpenChange(false)}
                disabled={loading}
              >
                {cancelLabel}
              </Button>
              <Button
                size='sm'
                bg={palette.ink}
                color={palette.textOnInk}
                _hover={{ bg: palette.inkHover }}
                loading={loading}
                onClick={onConfirm}
              >
                {confirmLabel}
              </Button>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  )
}
