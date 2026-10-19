import { useMemo } from 'react'

import { useAdminUsers } from './useAdmin.ts'
import { useMe } from './useMe.ts'
import { isAdmin } from '../lib/roles.ts'
import type { Role, User } from '../lib/types.ts'

export interface UserDirectory {
  label: (id: string | null | undefined) => string
  user: (id: string | null | undefined) => User | undefined
  isResolved: boolean
}

/**
 * Resolve user ids to display names.
 *
 * The backend only exposes a directory to admins (`GET /api/v1/users` is
 * admin-only), so agents and customers fall back to a neutral label for other
 * people's ids. This is an intentional, honest fallback — we never invent
 * names the API did not return.
 */
export function useUserDirectory(): UserDirectory {
  const me = useMe()
  const role: Role | undefined = me.data?.role
  const canList = isAdmin(role)
  const { data } = useAdminUsers({ limit: 100 }, canList)

  const map = useMemo(() => {
    const next = new Map<string, User>()
    for (const user of data ?? []) next.set(user.id, user)
    if (me.data) next.set(me.data.id, me.data)
    return next
  }, [data, me.data])

  return {
    isResolved: canList,
    user: (id) => (id ? map.get(id) : undefined),
    label: (id) => {
      if (!id) return '—'
      if (me.data && id === me.data.id) return 'You'
      const found = map.get(id)
      if (found) return found.full_name
      return `User ${id.slice(0, 8)}`
    },
  }
}
