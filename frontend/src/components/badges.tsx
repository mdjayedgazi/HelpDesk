import { Badge, type BadgeProps } from '@chakra-ui/react'
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

interface PillProps extends BadgeProps {
  tone?: 'default' | 'ink'
}

/**
 * Base monochrome pill. Status and priority are communicated through a
 * leading icon plus a clear text label rather than color alone.
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

export function StatusBadge({ status }: { status: TicketStatus }) {
  const meta = statusMeta[status]
  const Icon = meta.icon
  // Active states read as "ink" pills so the eye can find what needs work.
  const tone = status === 'OPEN' || status === 'IN_PROGRESS' ? 'ink' : 'default'
  return (
    <Pill tone={tone} title={`Status: ${meta.label}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const meta = priorityMeta[priority]
  const Icon = meta.icon
  return (
    <Pill tone={priority === 'URGENT' ? 'ink' : 'default'} title={`Priority: ${meta.label}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function RoleBadge({ role }: { role: Role }) {
  const meta = roleMeta[role]
  const Icon = meta.icon
  const prominent = role === 'admin' || role === 'owner'
  return (
    <Pill tone={prominent ? 'ink' : 'default'} title={`Role: ${meta.label}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function ActiveStatusBadge({ isActive }: { isActive: boolean }) {
  return (
    <Pill tone={isActive ? 'default' : 'ink'} title={isActive ? 'Active account' : 'Deactivated'}>
      <CircleDot size={12} strokeWidth={2.25} aria-hidden />
      {isActive ? 'Active' : 'Deactivated'}
    </Pill>
  )
}

export function CategoryBadge({ category }: { category: TicketCategory }) {
  const meta = categoryMeta[category]
  const Icon = meta.icon
  return (
    <Pill title={`Category: ${meta.label}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}

export function EscalationStatusBadge({ status }: { status: EscalationStatus }) {
  const meta = escalationStatusMeta[status]
  const Icon = meta.icon
  // Open states read as "ink" so reviewers can find what still needs action.
  const tone = status === 'PENDING' || status === 'IN_REVIEW' ? 'ink' : 'default'
  return (
    <Pill tone={tone} title={`Request status: ${meta.label}`}>
      <Icon size={12} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </Pill>
  )
}
