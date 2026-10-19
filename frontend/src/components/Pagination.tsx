import { Button, Flex, Text } from '@chakra-ui/react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { palette } from '../theme/palette.ts'

export function Pagination({
  page,
  pageSize,
  itemCount,
  hasNext,
  onPageChange,
}: {
  page: number
  pageSize: number
  itemCount: number
  hasNext: boolean
  onPageChange: (page: number) => void
}) {
  const hasPrev = page > 1
  const rangeStart = itemCount === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = (page - 1) * pageSize + itemCount

  return (
    <Flex
      align='center'
      justify='space-between'
      gap='4'
      pt='4'
      mt='1'
      borderTopWidth='1px'
      borderColor={palette.borderSubtle}
    >
      <Text fontSize='xs' color={palette.textMuted}>
        Showing{' '}
        <Text as='span' color={palette.textSecondary}>
          {rangeStart}
        </Text>
        –
        <Text as='span' color={palette.textSecondary}>
          {rangeEnd}
        </Text>
      </Text>
      <Flex align='center' gap='2'>
        <Button
          size='xs'
          variant='outline'
          borderColor={palette.border}
          disabled={!hasPrev}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={14} aria-hidden />
          Previous
        </Button>
        <Text fontSize='xs' color={palette.textSecondary} minW='12' textAlign='center'>
          Page {page}
        </Text>
        <Button
          size='xs'
          variant='outline'
          borderColor={palette.border}
          disabled={!hasNext}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <ChevronRight size={14} aria-hidden />
        </Button>
      </Flex>
    </Flex>
  )
}
