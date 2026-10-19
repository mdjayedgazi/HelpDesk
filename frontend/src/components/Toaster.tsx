import { createToaster, Portal, Stack, Toast, Toaster as ChakraToaster } from '@chakra-ui/react'

import { palette } from '../theme/palette.ts'

/**
 * App-wide toaster. Import `toaster` anywhere to raise a notification:
 *
 * ```ts
 * toaster.create({ title: 'Ticket created', type: 'success' })
 * ```
 */
export const toaster = createToaster({
  placement: 'bottom-end',
  pauseOnPageIdle: true,
  overlap: false,
  duration: 4500,
})

export function Toaster() {
  return (
    <Portal>
      <ChakraToaster toaster={toaster} insetInline={{ mdDown: '4' }}>
        {(toast) => (
          <Toast.Root
            width={{ base: 'full', sm: 'sm' }}
            borderWidth='1px'
            borderColor={palette.border}
            bg={palette.surface}
            color={palette.text}
            borderRadius='l2'
            boxShadow='0 8px 24px -12px rgba(0,0,0,0.18)'
          >
            <Toast.Indicator color={palette.text} />
            <Stack gap='0.5' flex='1' maxWidth='100%'>
              <Toast.Title fontSize='sm' fontWeight='medium'>
                {toast.title}
              </Toast.Title>
              {toast.description ? (
                <Toast.Description fontSize='xs' color={palette.textSecondary}>
                  {toast.description}
                </Toast.Description>
              ) : null}
            </Stack>
            <Toast.CloseTrigger color={palette.textMuted} />
          </Toast.Root>
        )}
      </ChakraToaster>
    </Portal>
  )
}
