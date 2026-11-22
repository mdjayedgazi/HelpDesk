import { Button, Flex, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import {
  canPaginate,
  clampPage,
  nextPage,
  pageRange,
  pageWindow,
  previousPage,
} from '../lib/pagination.ts'
import { palette } from '../theme/palette.ts'

type FullPagination = {
  page: number
  pageSize: number
  /** Total matching records across every page. */
  total: number
  /** Server-provided number of pages (>= 1). */
  totalPages: number
  /** True while the next page is being fetched; disables navigation. */
  isLoading?: boolean
  onPageChange: (page: number) => void
}

type LegacyPagination = {
  page: number
  pageSize: number
  /** Rows on the current page (for the "showing" range). */
  itemCount: number
  /** Whether a further page is known to exist. */
  hasNext: boolean
  isLoading?: boolean
  onPageChange: (page: number) => void
}

/**
 * Ticket-list pagination with circular Next/Previous.
 *
 * In **full mode** (`total` + `totalPages` present) every number comes from the
 * server's pagination metadata, never guessed from the page length. Next from
 * the last valid page wraps to page 1, Previous from page 1 wraps to the last
 * valid page, and only real page numbers are rendered (with ellipses in a
 * moving window). With zero or one page the controls are disabled.
 *
 * In **legacy mode** (`itemCount` + `hasNext`, used by list endpoints that do
 * not expose a total yet) the component keeps its previous behaviour: Previous
 * is disabled on page 1 and Next is disabled when `hasNext` is false. No
 * circular wrap is offered because the true last page is unknown.
 *
 * The component is presentation only: it never computes an offset or fetches.
 */
export function Pagination(props: FullPagination | LegacyPagination) {
  if ('totalPages' in props) {
    return <FullPager {...props} />
  }
  return <LegacyPager {...props} />
}

function FullPager({
  page,
  pageSize,
  total,
  totalPages,
  isLoading = false,
  onPageChange,
}: FullPagination) {
  const pages = Math.max(1, Math.floor(totalPages) || 1)
  const current = clampPage(page, pages)
  const interactive = canPaginate(pages)
  const { start, end } = pageRange(current, pageSize, total)
  const window = pageWindow(current, pages)

  const go = (target: number) => {
    const destination = clampPage(target, pages)
    if (destination === current || !interactive || isLoading) return
    onPageChange(destination)
  }

  return (
    <Shell
      summary={
        total === 0 ? (
          'No tickets'
        ) : (
          <>
            Showing{' '}
            <RangeValue>{start}</RangeValue>–<RangeValue>{end}</RangeValue> of{' '}
            <RangeValue>{total.toLocaleString('en-US')}</RangeValue>
          </>
        )
      }
      controls={
        <>
          <Button
            size='xs'
            variant='outline'
            borderColor={palette.border}
            disabled={!interactive || isLoading}
            onClick={() => go(previousPage(current, pages))}
            aria-label='Previous page'
          >
            <ChevronLeft size={14} aria-hidden />
            Previous
          </Button>

          <Flex
            as='nav'
            aria-label='Pagination'
            align='center'
            gap='1'
            maxW='100%'
            overflowX='auto'
            className='hd-tabs-scroll'
          >
            {window.map((item, index) =>
              item === 'ellipsis' ? (
                <Text
                  key={`ellipsis-${index}`}
                  as='span'
                  px='1'
                  fontSize='xs'
                  color={palette.textFaint}
                  aria-hidden
                >
                  …
                </Text>
              ) : (
                <Button
                  key={item}
                  size='xs'
                  variant='ghost'
                  minW='8'
                  px='2'
                  aria-label={`Page ${item}`}
                  aria-current={item === current ? 'page' : undefined}
                  disabled={isLoading}
                  onClick={() => go(item)}
                  bg={item === current ? palette.surfaceMuted : 'transparent'}
                  color={item === current ? palette.text : palette.textSecondary}
                  fontWeight={item === current ? 'semibold' : 'regular'}
                  borderWidth='1px'
                  borderColor={item === current ? palette.border : 'transparent'}
                  _hover={{ bg: palette.hover, color: palette.text }}
                  _focusVisible={{
                    outline: '2px solid',
                    outlineColor: palette.focus,
                    outlineOffset: '2px',
                  }}
                >
                  {item}
                </Button>
              ),
            )}
          </Flex>

          <Text
            fontSize='2xs'
            color={palette.textFaint}
            minW='14'
            textAlign='center'
            fontVariantNumeric='tabular-nums'
          >
            Page {current} of {pages}
          </Text>

          <Button
            size='xs'
            variant='outline'
            borderColor={palette.border}
            disabled={!interactive || isLoading}
            onClick={() => go(nextPage(current, pages))}
            aria-label='Next page'
          >
            Next
            <ChevronRight size={14} aria-hidden />
          </Button>
        </>
      }
    />
  )
}

function LegacyPager({
  page,
  pageSize,
  itemCount,
  hasNext,
  isLoading = false,
  onPageChange,
}: LegacyPagination) {
  const hasPrev = page > 1
  const rangeStart = itemCount === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = (page - 1) * pageSize + itemCount

  return (
    <Shell
      summary={
        <>
          Showing <RangeValue>{rangeStart}</RangeValue>–<RangeValue>{rangeEnd}</RangeValue>
        </>
      }
      controls={
        <>
          <Button
            size='xs'
            variant='outline'
            borderColor={palette.border}
            disabled={!hasPrev || isLoading}
            onClick={() => onPageChange(page - 1)}
            aria-label='Previous page'
          >
            <ChevronLeft size={14} aria-hidden />
            Previous
          </Button>
          <Text
            fontSize='xs'
            color={palette.textSecondary}
            minW='12'
            textAlign='center'
            fontVariantNumeric='tabular-nums'
          >
            Page {page}
          </Text>
          <Button
            size='xs'
            variant='outline'
            borderColor={palette.border}
            disabled={!hasNext || isLoading}
            onClick={() => onPageChange(page + 1)}
            aria-label='Next page'
          >
            Next
            <ChevronRight size={14} aria-hidden />
          </Button>
        </>
      }
    />
  )
}

function Shell({ summary, controls }: { summary: ReactNode; controls: ReactNode }) {
  return (
    <Flex
      align='center'
      justify='space-between'
      gap='4'
      wrap='wrap'
      pt='4'
      mt='1'
      borderTopWidth='1px'
      borderColor={palette.borderSubtle}
    >
      <Text fontSize='xs' color={palette.textMuted} fontVariantNumeric='tabular-nums'>
        {summary}
      </Text>
      <Flex align='center' gap='1.5'>
        {controls}
      </Flex>
    </Flex>
  )
}

function RangeValue({ children }: { children: ReactNode }) {
  return (
    <Text as='span' color={palette.textSecondary}>
      {children}
    </Text>
  )
}
