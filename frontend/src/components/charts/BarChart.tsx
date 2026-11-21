import { Box, Flex, Text } from '@chakra-ui/react'

import { useDelayedEntrance } from '../../hooks/useEntrance.ts'
import { motionVars, stagger } from '../../theme/motion.ts'
import { palette } from '../../theme/palette.ts'
import { AnimatedNumber } from '../motion/AnimatedNumber.tsx'
import { ChartDataTable } from './ChartCard.tsx'

/**
 * Horizontal composition bars.
 *
 * Used for priority pressure and category mix. Bars are proportional to the
 * largest value (not to the total) so a long tail stays visible, and each row
 * still shows its absolute count and share of the total so the visual scale
 * cannot be misread. Bars are rendered with a div rather than SVG because they
 * are simple rectangles that reflow better in a responsive column.
 *
 * On first appearance each bar grows from zero to exactly `value / max` using
 * `transform: scaleX`, so the final geometry is the real proportion — with no
 * minimum width. A 1-in-100 value is drawn as 1% of the track; it stays legible
 * through the exact count and share printed beside the row, never through
 * falsified geometry. Rows are staggered by a few tens of milliseconds and the
 * animation never repeats.
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
        {items.map((item, index) => (
          <BarRow
            key={item.key}
            item={item}
            index={index}
            total={total}
            max={max}
            onSelect={onSelect}
            valueSuffix={valueSuffix}
          />
        ))}
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

function BarRow({
  item,
  index,
  total,
  max,
  onSelect,
  valueSuffix,
}: {
  item: BarItem
  index: number
  total: number
  max: number
  onSelect?: (item: BarItem) => void
  valueSuffix?: string
}) {
  const entered = useDelayedEntrance(stagger(index))
  // The bar is exactly `value / max`. There is deliberately no minimum visible
  // width: a 1-in-100 count must render as 1% of the track, not as an arbitrary
  // 4%. Small values stay legible through the exact count and share printed
  // beside the row, never through falsified geometry.
  const ratio = max > 0 ? Math.min(1, Math.max(0, item.value / max)) : 0
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
            <AnimatedNumber value={item.value} duration={520} />
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
      <Box
        height='2'
        borderRadius='full'
        bg={palette.inset}
        overflow='hidden'
        role='presentation'
      >
        <Box
          height='100%'
          width='100%'
          bg={item.color}
          borderRadius='full'
          style={{
            transform: `scaleX(${entered ? ratio : 0})`,
            transformOrigin: 'left center',
            transition: `transform ${motionVars.chart} ${motionVars.easeOut}`,
          }}
        />
      </Box>
    </Flex>
  )

  return (
    <Box as='li'>
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
}
