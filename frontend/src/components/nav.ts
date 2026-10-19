import {
  Bell,
  Gauge,
  Inbox,
  LayoutDashboard,
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
}

export interface NavSection {
  label: string
  items: NavItem[]
}

/**
 * Navigation is derived from the *application role returned by the backend*,
 * never from anything client-controlled. The backend independently enforces
 * every permission; this only shapes what the user sees.
 */
export function navSectionsForRole(role: Role): NavSection[] {
  if (role === 'admin' || role === 'owner') {
    return [
      {
        label: 'Overview',
        items: [{ label: 'Dashboard', to: '/', icon: Gauge, end: true }],
      },
      {
        label: 'Management',
        items: [
          { label: 'Tickets', to: '/tickets', icon: Ticket },
          { label: 'Users', to: '/admin/users', icon: Users },
          { label: 'Account requests', to: '/account-requests', icon: ShieldQuestion },
        ],
      },
      {
        label: 'Messaging',
        items: [
          {
            // The Owner *answers* the private staff channel from the inbox;
            // admins start/reply in their own thread with the Owner.
            label: role === 'owner' ? 'Owner inbox' : 'Message Owner',
            to: '/messages',
            icon: Mail,
          },
        ],
      },
      {
        label: 'Administration',
        items: [{ label: 'Admin overview', to: '/admin', icon: LayoutDashboard, end: true }],
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
        items: [{ label: 'Dashboard', to: '/', icon: Gauge, end: true }],
      },
      {
        label: 'Workspace',
        items: [
          { label: 'My queue', to: '/queue', icon: Inbox },
          { label: 'All tickets', to: '/tickets', icon: LayoutList },
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
      items: [{ label: 'Dashboard', to: '/', icon: Gauge, end: true }],
    },
    {
      label: 'Support',
      items: [
        { label: 'My tickets', to: '/tickets', icon: Ticket },
        { label: 'New ticket', to: '/tickets/new', icon: Plus, end: true },
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
  if (pathname === '/') return 'Dashboard'
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
