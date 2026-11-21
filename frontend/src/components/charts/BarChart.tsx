import { Box, Flex, Text } from '@chakra-ui/react'

import { palette } from '../../theme/palette.ts'
import { ChartDataTable } from './ChartCard.tsx'

/**
 * Horizontal composition bars.
 *
 * Used for priority pressure and category mix. Bars are proportional to the
 * largest value (not to the total) so a long tail stays visible, and each row
 * still shows its absolute count and share of the total so the visual scale
 * cannot be misread. Bars are rendered with a div rather than SVG because they
 * are simple rectangles that reflow better in a responsive column.
 */

export interface BarItem {
  key: string
  label: string
  value: number
  color: string
  /** Optional short note shown at the right, e.g. "unassigned". */
  hint?: string
}

export function BarChart({
  items,
  ariaLabel,
  onSelect,
  valueSuffix,
}: {
  items: BarItem[]
  ariaLabel: string
  onSelect?: (item: BarItem) => void
  valueSuffix?: string
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0)
  const max = Math.max(1, ...items.map((item) => item.value))

  return (
    <Box minW='0'>
      <Box as='ul' listStyleType='none' m='0' p='0'>
        {items.map((item) => {
          const widthPct = Math.max(item.value > 0 ? 4 : 0, Math.round((item.value / max) * 100))
          const share = total > 0 ? Math.round((item.value / total) * 100) : 0
          const inner = (
            <Flex direction='column' gap='1.5' py='1.5' width='full' textAlign='left'>
              <Flex align='baseline' gap='2' justify='space-between'>
                <Flex align='center' gap='2' minW='0'>
                  <Box boxSize='2' borderRadius='full' bg={item.color} flexShrink={0} aria-hidden />
                  <Text fontSize='xs' color={palette.textSecondary} truncate>
                    {item.label}
                  </Text>
                  {item.hint ? (
                    <Text fontSize='2xs' color={palette.textFaint} flexShrink={0}>
                      {item.hint}
                    </Text>
                  ) : null}
                </Flex>
                <Flex align='baseline' gap='1.5' flexShrink={0}>
                  <Text
                    fontSize='xs'
                    fontWeight='medium'
                    color={palette.text}
                    fontVariantNumeric='tabular-nums'
                  >
                    {item.value}
                    {valueSuffix ? (
                      <Text as='span' color={palette.textMuted}>
                        {valueSuffix}
                      </Text>
                    ) : null}
                  </Text>
                  <Text
                    fontSize='2xs'
                    color={palette.textFaint}
                    fontVariantNumeric='tabular-nums'
                    minW='7'
                    textAlign='right'
                    display={{ base: 'none', sm: 'block' }}
                  >
                    {share}%
                  </Text>
                </Flex>
              </Flex>
              <Box height='2' borderRadius='full' bg={palette.inset} overflow='hidden'>
                <Box
                  height='100%'
                  width={`${widthPct}%`}
                  bg={item.color}
                  borderRadius='full'
                  transition='width var(--hd-dur-3) var(--hd-ease-out)'
                />
              </Box>
            </Flex>
          )

          return (
            <Box as='li' key={item.key}>
              {onSelect ? (
                <Box
                  asChild
                  width='full'
                  cursor='pointer'
                  borderRadius='l2'
                  _hover={{ bg: palette.hover }}
                  _focusVisible={{ outline: '2px solid', outlineColor: palette.focus, outlineOffset: '2px' }}
                >
                  <button type='button' onClick={() => onSelect(item)} style={{ textAlign: 'left' }}>
                    {inner}
                  </button>
                </Box>
              ) : (
                inner
              )}
            </Box>
          )
        })}
      </Box>

      <ChartDataTable
        caption={ariaLabel}
        columns={['Group', 'Tickets', 'Share']}
        rows={items.map((item) => [
          item.label,
          item.value,
          `${total > 0 ? Math.round((item.value / total) * 100) : 0}%`,
        ])}
      />
    </Box>
  )
}
