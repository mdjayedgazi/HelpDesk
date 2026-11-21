import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import type { ReactNode } from 'react'

import { palette } from '../../theme/palette.ts'
import { type Tone, tones } from '../../theme/statusTone.ts'
import { Surface } from '../Surface.tsx'

/**
 * Shared chart chrome.
 *
 * Every chart on the dashboards lives in a `ChartCard` so the title, the
 * "what question does this answer" subtitle, the legend and the empty/loading
 * treatment are consistent across roles. Charts are rendered as inline SVG with
 * a text summary and a `<table>` fallback, so they are readable by a screen
 * reader and by anyone with images disabled.
 */

export function ChartCard({
  title,
  question,
  action,
  legend,
  children,
  minH,
}: {
  title: string
  /** The operational question this chart answers, shown under the title. */
  question?: string
  action?: ReactNode
  legend?: ReactNode
  children: ReactNode
  minH?: string
}) {
  return (
    <Surface p={{ base: '4', md: '5' }} minW='0'>
      <Stack gap='4' minW='0'>
        <Flex align='flex-start' justify='space-between' gap='3' wrap='wrap'>
          <Stack gap='0.5' minW='0'>
            <Text fontSize='sm' fontWeight='semibold' color={palette.text} letterSpacing='-0.01em'>
              {title}
            </Text>
            {question ? (
              <Text fontSize='xs' color={palette.textMuted}>
                {question}
              </Text>
            ) : null}
          </Stack>
          {action}
        </Flex>
        <Box minW='0' minH={minH}>
          {children}
        </Box>
        {legend ? legend : null}
      </Stack>
    </Surface>
  )
}

export function ChartEmpty({
  title = 'No data yet',
  description,
}: {
  title?: string
  description?: string
}) {
  return (
    <Flex
      direction='column'
      align='center'
      justify='center'
      textAlign='center'
      minH='40'
      gap='1'
      px='4'
      borderWidth='1px'
      borderStyle='dashed'
      borderColor={palette.borderSubtle}
      borderRadius='l2'
    >
      <Text fontSize='sm' fontWeight='medium' color={palette.textSecondary}>
        {title}
      </Text>
      {description ? (
        <Text fontSize='xs' color={palette.textMuted} maxW='xs'>
          {description}
        </Text>
      ) : null}
    </Flex>
  )
}

export function ChartLegend({
  items,
  onToggle,
}: {
  items: Array<{ label: string; value?: string | number; tone?: Tone; color?: string }>
  onToggle?: (label: string) => void
}) {
  return (
    <Flex gap='4' wrap='wrap'>
      {items.map((item) => {
        const swatch = item.color ?? tones[item.tone ?? 'neutral'].solid
        return (
          <Flex
            key={item.label}
            as={onToggle ? 'button' : 'div'}
            align='center'
            gap='2'
            fontSize='xs'
            color={palette.textSecondary}
            onClick={onToggle ? () => onToggle(item.label) : undefined}
            cursor={onToggle ? 'pointer' : undefined}
            bg='transparent'
            border='none'
            p='0'
          >
            <Box boxSize='2' borderRadius='full' bg={swatch} flexShrink={0} aria-hidden />
            <Text as='span' color={palette.textSecondary}>
              {item.label}
            </Text>
            {item.value !== undefined ? (
              <Text as='span' color={palette.text} fontWeight='medium' fontVariantNumeric='tabular-nums'>
                {item.value}
              </Text>
            ) : null}
          </Flex>
        )
      })}
    </Flex>
  )
}

/**
 * A visually hidden data table that backs every chart.
 *
 * The chart SVG is marked `aria-hidden`, and this table is the accessible
 * representation of the same numbers: real row/column headers, no ARIA needed.
 */
export function ChartDataTable({
  caption,
  columns,
  rows,
}: {
  caption: string
  columns: string[]
  rows: Array<Array<string | number>>
}) {
  return (
    <Box
      as='table'
      // Visible to assistive technology and to users who print the page, but
      // not part of the visual layout (the chart is the visual encoding).
      position='absolute'
      width='1px'
      height='1px'
      p='0'
      m='-1px'
      overflow='hidden'
      clip='rect(0, 0, 0, 0)'
      whiteSpace='nowrap'
      borderWidth='0'
    >
      <caption>{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope='col'>
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {row.map((cell, cellIndex) =>
              cellIndex === 0 ? (
                <th key={cellIndex} scope='row'>
                  {cell}
                </th>
              ) : (
                <td key={cellIndex}>{cell}</td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </Box>
  )
}
