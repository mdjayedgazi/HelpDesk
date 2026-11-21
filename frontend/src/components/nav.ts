import {
  Bell,
  Gauge,
  Inbox,
  LayoutList,
  Mail,
  Plus,
  ShieldQuestion,
  Ticket,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react'

import type { Role } from '../lib/types.ts'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** Match only the exact path (used for index-like routes). */
  end?: boolean
  /** Optional short description for the mobile drawer. */
  hint?: string
}

export interface NavSection {
  label: string
  items: NavItem[]
}

/**
 * Navigation is derived from the *application role returned by the backend*,
 * never from anything client-controlled. The backend independently enforces
 * every permission; this only shapes what the user sees.
 *
 * Admin and owner share one coherent structure: the previous layout exposed
 * "Dashboard" and "Admin overview" as two routes rendering the same component,
 * which made it impossible to know which one was "home". There is now a single
 * dashboard destination and the administrative tools live in one section.
 */
export function navSectionsForRole(role: Role): NavSection[] {
  if (role === 'admin' || role === 'owner') {
    return [
      {
        label: 'Overview',
        items: [
          {
            label: 'Dashboard',
            to: '/dashboard',
            icon: Gauge,
            end: true,
            hint: 'Support health and workload',
          },
        ],
      },
      {
        label: 'Support',
        items: [
          { label: 'Tickets', to: '/tickets', icon: Ticket, hint: 'All customer requests' },
          {
            label: 'Account requests',
            to: '/account-requests',
            icon: ShieldQuestion,
            hint: 'Privileged account actions',
          },
        ],
      },
      {
        label: 'Management',
        items: [
          { label: 'Users', to: '/admin/users', icon: Users, hint: 'Accounts, roles and access' },
          {
            // The Owner *answers* the private staff channel from the inbox;
            // admins start/reply in their own thread with the Owner.
            label: role === 'owner' ? 'Owner inbox' : 'Message Owner',
            to: '/messages',
            icon: Mail,
            hint: 'Private staff messaging',
          },
        ],
      },
      {
        label: 'Account',
        items: [
          { label: 'Notifications', to: '/notifications', icon: Bell },
          { label: 'Profile', to: '/profile', icon: UserRound },
        ],
      },
    ]
  }

  if (role === 'agent') {
    return [
      {
        label: 'Overview',
        items: [
          {
            label: 'Dashboard',
            to: '/dashboard',
            icon: Gauge,
            end: true,
            hint: 'Your workload at a glance',
          },
        ],
      },
      {
        label: 'Workspace',
        items: [
          { label: 'My queue', to: '/queue', icon: Inbox, hint: 'Claim and work tickets' },
          { label: 'All tickets', to: '/tickets', icon: LayoutList, hint: 'Everything you can see' },
          { label: 'Account requests', to: '/account-requests', icon: ShieldQuestion },
          { label: 'Message Owner', to: '/messages', icon: Mail },
        ],
      },
      {
        label: 'Account',
        items: [
          { label: 'Notifications', to: '/notifications', icon: Bell },
          { label: 'Profile', to: '/profile', icon: UserRound },
        ],
      },
    ]
  }

  // Customers have no private staff channel: there is deliberately no
  // "Message the Owner" entry here, matching the backend (customers receive
  // 403 from every staff-messaging endpoint).
  return [
    {
      label: 'Overview',
      items: [
        {
          label: 'Dashboard',
          to: '/dashboard',
          icon: Gauge,
          end: true,
          hint: 'Your requests at a glance',
        },
      ],
    },
    {
      label: 'Support',
      items: [
        { label: 'My tickets', to: '/tickets', icon: Ticket, hint: 'Track your requests' },
        { label: 'New ticket', to: '/tickets/new', icon: Plus, end: true, hint: 'Ask for help' },
      ],
    },
    {
      label: 'Account',
      items: [
        { label: 'Notifications', to: '/notifications', icon: Bell },
        { label: 'Profile', to: '/profile', icon: UserRound },
      ],
    },
  ]
}

export function sectionTitleForPath(pathname: string): string {
  if (pathname === '/dashboard') return 'Dashboard'
  if (pathname.startsWith('/admin/users')) return 'Users'
  if (pathname.startsWith('/admin')) return 'Admin'
  if (pathname.startsWith('/tickets/new')) return 'New ticket'
  if (pathname.startsWith('/tickets/')) return 'Ticket'
  if (pathname.startsWith('/tickets')) return 'Tickets'
  if (pathname.startsWith('/queue')) return 'My queue'
  if (pathname.startsWith('/messages')) return 'Messages'
  if (pathname.startsWith('/account-requests')) return 'Account requests'
  if (pathname.startsWith('/notifications')) return 'Notifications'
  if (pathname.startsWith('/profile')) return 'Profile'
  return 'HelpDesk'
}

/** The nav section a path belongs to, used for the top bar's context line. */
export function navSectionForPath(role: Role, pathname: string): string | null {
  const sections = navSectionsForRole(role)
  for (const section of sections) {
    for (const item of section.items) {
      if (item.end ? pathname === item.to : pathname.startsWith(item.to)) {
        return section.label
      }
    }
  }
  return null
}
