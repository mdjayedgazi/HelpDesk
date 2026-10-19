import {
  Box,
  Button,
  Center,
  type CenterProps,
  Flex,
  Skeleton,
  Spinner,
  Stack,
  Text,
} from '@chakra-ui/react'
import { Lock, RefreshCw, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

export function LoadingState({
  label = 'Loading…',
  minHeight = '40vh',
}: {
  label?: string
  minHeight?: string
}) {
  return (
    <Center minHeight={minHeight} gap='3' flexDirection='column'>
      <Spinner size='sm' color={palette.textMuted} />
      <Text fontSize='xs' color={palette.textMuted} letterSpacing='0.02em'>
        {label}
      </Text>
    </Center>
  )
}

export function InlineSpinner() {
  return <Spinner size='xs' color='currentColor' />
}

export function ErrorState({
  title = 'Something went wrong',
  description,
  onRetry,
  action,
}: {
  title?: string
  description?: string
  onRetry?: () => void
  action?: ReactNode
}) {
  return (
    <Center minHeight='40vh' flexDirection='column' textAlign='center' px='6'>
      <Stack gap='3' align='center' maxW='sm'>
        <Text fontSize='md' fontWeight='medium' color={palette.text}>
          {title}
        </Text>
        {description ? (
          <Text fontSize='sm' color={palette.textSecondary}>
            {description}
          </Text>
        ) : null}
        {onRetry || action ? (
          <Flex gap='2' pt='1'>
            {onRetry ? (
              <Button size='sm' variant='outline' borderColor={palette.border} onClick={onRetry}>
                <RefreshCw size={14} aria-hidden />
                Try again
              </Button>
            ) : null}
            {action}
          </Flex>
        ) : null}
      </Stack>
    </Center>
  )
}

export interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  compact?: boolean
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <Box
      borderWidth='1px'
      borderColor={palette.border}
      borderStyle='dashed'
      borderRadius='l3'
      bg={palette.surface}
      px='6'
      py={compact ? '8' : '14'}
    >
      <Stack gap='4' align='center' textAlign='center' maxW='sm' mx='auto'>
        {Icon ? (
          <Center
            boxSize='10'
            borderRadius='full'
            borderWidth='1px'
            borderColor={palette.border}
            bg={palette.surfaceMuted}
            color={palette.textSecondary}
          >
            <Icon size={18} strokeWidth={1.75} aria-hidden />
          </Center>
        ) : null}
        <Stack gap='1'>
          <Text fontSize='sm' fontWeight='medium' color={palette.text}>
            {title}
          </Text>
          {description ? (
            <Text fontSize='sm' color={palette.textSecondary}>
              {description}
            </Text>
          ) : null}
        </Stack>
        {action}
      </Stack>
    </Box>
  )
}

export function AccessDenied({
  title = 'Access denied',
  description = 'You do not have permission to view this page.',
}: {
  title?: string
  description?: string
}) {
  return (
    <Center minHeight='50vh' flexDirection='column' textAlign='center' px='6'>
      <Stack gap='4' align='center' maxW='md'>
        <Center
          boxSize='11'
          borderRadius='full'
          borderWidth='1px'
          borderColor={palette.border}
          bg={palette.surface}
          color={palette.text}
        >
          <Lock size={18} strokeWidth={1.75} aria-hidden />
        </Center>
        <Stack gap='1'>
          <Text fontSize='lg' fontWeight='medium'>
            {title}
          </Text>
          <Text fontSize='sm' color={palette.textSecondary}>
            {description}
          </Text>
        </Stack>
      </Stack>
    </Center>
  )
}

export function TableSkeleton({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <Stack gap='0' borderTopWidth='1px' borderColor={palette.border}>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <Flex
          key={rowIndex}
          gap='6'
          px='4'
          py='3.5'
          borderBottomWidth='1px'
          borderColor={palette.borderSubtle}
        >
          {Array.from({ length: columns }).map((__, colIndex) => (
            <Skeleton
              key={colIndex}
              height='3.5'
              flex={colIndex === 0 ? 2 : 1}
              bg={palette.inset}
            />
          ))}
        </Flex>
      ))}
    </Stack>
  )
}

export function BlockSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <Stack gap='3'>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          height='4'
          width={index === lines - 1 ? '60%' : '100%'}
          bg={palette.inset}
        />
      ))}
    </Stack>
  )
}

export function Page({ children, ...rest }: CenterProps) {
  return <Center {...rest}>{children}</Center>
}
