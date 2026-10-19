import { Field, Input, NativeSelect, Stack, Textarea } from '@chakra-ui/react'
import { forwardRef, type ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

export interface FormFieldProps {
  label: ReactNode
  htmlFor?: string
  error?: string
  helperText?: ReactNode
  required?: boolean
  children: ReactNode
}

export function FormField({
  label,
  htmlFor,
  error,
  helperText,
  required,
  children,
}: FormFieldProps) {
  return (
    <Field.Root invalid={Boolean(error)} required={required} gap='1.5'>
      <Field.Label htmlFor={htmlFor} fontSize='sm' fontWeight='medium' color={palette.text}>
        {label}
        {required ? <Field.RequiredIndicator color={palette.textMuted} /> : null}
      </Field.Label>
      {children}
      {error ? (
        <Field.ErrorText fontSize='xs' role='alert'>
          {error}
        </Field.ErrorText>
      ) : helperText ? (
        <Field.HelperText fontSize='xs' color={palette.textMuted}>
          {helperText}
        </Field.HelperText>
      ) : null}
    </Field.Root>
  )
}

const inputStyles = {
  bg: palette.surface,
  borderColor: palette.border,
  borderRadius: 'l2',
  fontSize: 'sm',
  _placeholder: { color: palette.textFaint },
  _hover: { borderColor: palette.borderStrong },
  _focus: { borderColor: palette.ink },
} as const

export const TextInput = forwardRef<HTMLInputElement, React.ComponentProps<typeof Input>>(
  function TextInput(props, ref) {
    return <Input ref={ref} {...inputStyles} {...props} />
  },
)

export const TextAreaInput = forwardRef<HTMLTextAreaElement, React.ComponentProps<typeof Textarea>>(
  function TextAreaInput(props, ref) {
    return <Textarea ref={ref} {...inputStyles} {...props} />
  },
)

export function SelectInput({ children, ...rest }: React.ComponentProps<typeof NativeSelect.Root>) {
  return (
    <NativeSelect.Root size='sm' {...rest}>
      <NativeSelect.Field {...inputStyles}>{children}</NativeSelect.Field>
      <NativeSelect.Indicator color={palette.textMuted} />
    </NativeSelect.Root>
  )
}

export function FormStack({ children }: { children: ReactNode }) {
  return <Stack gap='5'>{children}</Stack>
}
