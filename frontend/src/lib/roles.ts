import type { Role } from './types.ts'

/**
 * Whether the role works on tickets. The Owner is a super-administrator, so it
 * carries every administrative capability (mirrors `app.core.permissions`).
 */
export function isStaff(role: Role | undefined | null): boolean {
  return role === 'agent' || role === 'admin' || role === 'owner'
}

/** Whether the role has administrative capabilities (ADMIN or OWNER). */
export function isAdmin(role: Role | undefined | null): boolean {
  return role === 'admin' || role === 'owner'
}

export function isAgent(role: Role | undefined | null): boolean {
  return role === 'agent'
}

/** The permanent, unique top-level role. */
export function isOwner(role: Role | undefined | null): boolean {
  return role === 'owner'
}

export function canManageTickets(role: Role | undefined | null): boolean {
  return isStaff(role)
}

/** Whether the role may change other users' roles and account status. */
export function canManageUsers(role: Role | undefined | null): boolean {
  return role === 'owner'
}

/** The landing route for a role. The dashboard itself is role-aware. */
export function homePathForRole(_role: Role): string {
  return '/'
}
