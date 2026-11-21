import { Badge, type BadgeProps, Box, Flex } from '@chakra-ui/react'
import {
  ArrowDown,
  ArrowUp,
  Ban,
  Bug,
  CheckCheck,
  CheckCircle2,
  CircleDot,
  CircleDashed,
  CircleHelp,
  Clock,
  CloudOff,
  CreditCard,
  Crown,
  Equal,
  KeyRound,
  Lock,
  Search,
  ShieldCheck,
  TriangleAlert,
  User,
  UserCog,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { palette } from '../theme/palette.ts'
import { type Tone, priorityTone, statusTone, tones } from '../theme/statusTone.ts'
import {
  escalationStatusLabels,
  priorityLabels,
  roleLabels,
  statusLabels,
  ticketCategoryLabels,
} from '../lib/format.ts'
import type {
  EscalationStatus,
  Role,
  TicketCategory,
  TicketPriority,
  TicketStatus,
} from '../lib/types.ts'

interface Meta {
  label: string
  icon: LucideIcon
}

const statusMeta: Record<TicketStatus, Meta> = {
  OPEN: { label: statusLabels.OPEN, icon: CircleDot },
  IN_PROGRESS: { label: statusLabels.IN_PROGRESS, icon: CircleDashed },
  WAITING_ON_CUSTOMER: { label: statusLabels.WAITING_ON_CUSTOMER, icon: Clock },
  RESOLVED: { label: statusLabels.RESOLVED, icon: CheckCircle2 },
  CLOSED: { label: statusLabels.CLOSED, icon: Lock },
}

const priorityMeta: Record<TicketPriority, Meta> = {
  LOW: { label: priorityLabels.LOW, icon: ArrowDown },
  NORMAL: { label: priorityLabels.NORMAL, icon: Equal },
  HIGH: { label: priorityLabels.HIGH, icon: ArrowUp },
  URGENT: { label: priorityLabels.URGENT, icon: TriangleAlert },
}

const roleMeta: Record<Role, Meta> = {
  customer: { label: roleLabels.customer, icon: User },
  agent: { label: roleLabels.agent, icon: Wrench },
  admin: { label: roleLabels.admin, icon: ShieldCheck },
  owner: { label: roleLabels.owner, icon: Crown },
}

const categoryMeta: Record<TicketCategory, Meta> = {
  BILLING: { label: ticketCategoryLabels.BILLING, icon: CreditCard },
  ACCOUNT_ACCESS: { label: ticketCategoryLabels.ACCOUNT_ACCESS, icon: KeyRound },
  TECHNICAL: { label: ticketCategoryLabels.TECHNICAL, icon: Wrench },
  OUTAGE: { label: ticketCategoryLabels.OUTAGE, icon: CloudOff },
  BUG: { label: ticketCategoryLabels.BUG, icon: Bug },
  ACCOUNT_MANAGEMENT: { label: ticketCategoryLabels.ACCOUNT_MANAGEMENT, icon: UserCog },
  OTHER: { label: ticketCategoryLabels.OTHER, icon: CircleHelp },
}

const escalationStatusMeta: Record<EscalationStatus, Meta> = {
  PENDING: { label: escalationStatusLabels.PENDING, icon: Clock },
  IN_REVIEW: { label: escalationStatusLabels.IN_REVIEW, icon: Search },
  APPROVED: { label: escalationStatusLabels.APPROVED, icon: CheckCircle2 },
  REJECTED: { label: escalationStatusLabels.REJECTED, icon: Ban },
  COMPLETED: { label: escalationStatusLabels.COMPLETED, icon: CheckCheck },
}

const escalationTone: Record<EscalationStatus, Tone> = {
  PENDING: 'warning',
  IN_REVIEW: 'info',
  APPROVED: 'success',
  REJECTED: 'neutral',
  COMPLETED: 'success',
}

interface PillProps extends BadgeProps {
  tone?: 'default' | 'ink'
}

/**
 * Base neutral pill used where no status semantics apply.
 *
 * Border + text only, so it stays quiet against the semantic status badges.
 */
export function Pill({ tone = 'default', children, ...rest }: PillProps) {
  return (
    <Badge
      variant='outline'
      size='md'
      borderRadius='full'
      borderWidth='1px'
      borderColor={palette.border}
      bg={tone === 'ink' ? palette.ink : palette.surface}
      color={tone === 'ink' ? palette.textOnInk : palette.text}
      fontWeight='medium'
      letterSpacing='0.01em'
      textTransform='none'
      px='2.5'
      py='0.5'
      gap='1.5'
      {...rest}
    >
      {children}
    </Badge>
  )
}

/**
 * Semantically toned pill.
 *
 * Colour is never the only signal: every badge carries a leading icon and a
 * text label, so it is still readable with colour vision deficiency, in
 * grayscale print, and on low-quality displays.
 */
function TonePill({
  tone,
  icon: Icon,
  title,
  children,
}: {
  tone: Tone
  icon: LucideIcon
  title: string
  children: React.ReactNode
}) {
  const style = tones[tone]
  return (
    <Badge
      as='span'
      title={title}
      variant='outline'
      size='md'
      borderRadius='full'
      borderWidth='1px'
      borderColor={tone === 'neutral' ? palette.border : style.border}
      bg={tone === 'neutral' ? palette.surface : style.soft}
      color={tone === 'neutral' ? palette.textSecondary : style.solid}
      fontWeight='medium'
      letterSpacing='0.01em'
      textTransform='none'
      px='2.5'
      py='0.5'
      gap='1.5'
      whiteSpace='nowrap'
    >
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {children}
    </Badge>
  )
}

export function StatusBadge({ status }: { status: TicketStatus }) {
  const meta = statusMeta[status]
  return (
    <TonePill tone={statusTone[status]} icon={meta.icon} title={`Status: ${meta.label}`}>
      {meta.label}
    </TonePill>
  )
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const meta = priorityMeta[priority]
  return (
    <TonePill tone={priorityTone[priority]} icon={meta.icon} title={`Priority: ${meta.label}`}>
      {meta.label}
    </TonePill>
  )
}

export function RoleBadge({ role }: { role: Role }) {
  const meta = roleMeta[role]
  // Administrative roles read as ink pills: the only place ink doubles as a
  // capability signal.
  const prominent = role === 'admin' || role === 'owner'
  return (
    <Pill tone={prominent ? 'ink' : 'default'} title={`Role: ${meta.label}`}>
      <meta.icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function ActiveStatusBadge({ isActive }: { isActive: boolean }) {
  return (
    <Flex align='center' gap='1.5' as='span'>
      <Box
        boxSize='1.5'
        borderRadius='full'
        bg={isActive ? palette.semantic.success : palette.textFaint}
        aria-hidden
      />
      <Pill tone={isActive ? 'default' : 'ink'} title={isActive ? 'Active account' : 'Deactivated'}>
        <CircleDot size={12} strokeWidth={2.25} aria-hidden />
        {isActive ? 'Active' : 'Deactivated'}
      </Pill>
    </Flex>
  )
}

export function CategoryBadge({ category }: { category: TicketCategory }) {
  const meta = categoryMeta[category]
  return (
    <Pill title={`Category: ${meta.label}`}>
      <meta.icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function EscalationStatusBadge({ status }: { status: EscalationStatus }) {
  const meta = escalationStatusMeta[status]
  return (
    <TonePill tone={escalationTone[status]} icon={meta.icon} title={`Request status: ${meta.label}`}>
      {meta.label}
    </TonePill>
  )
}
