import { describe, expect, it } from 'vite-plus/test'

import {
  canManageTickets,
  canManageUsers,
  isAdmin,
  isAgent,
  isOwner,
  isStaff,
} from './roles.ts'

describe('role-derived controls', () => {
  it.each([
    ['customer', false],
    ['agent', true],
    ['admin', true],
    ['owner', true],
  ] as const)('canManageTickets(%s) is %s', (role, expected) => {
    expect(canManageTickets(role)).toBe(expected)
  })

  it.each([
    ['customer', false],
    ['agent', false],
    ['admin', false],
    ['owner', true],
  ] as const)('canManageUsers(%s) is %s', (role, expected) => {
    expect(canManageUsers(role)).toBe(expected)
  })

  it('fails closed for a missing role', () => {
    expect(isStaff(undefined)).toBe(false)
    expect(isAdmin(null)).toBe(false)
    expect(isOwner(undefined)).toBe(false)
    expect(isAgent(null)).toBe(false)
    expect(canManageTickets(undefined)).toBe(false)
    expect(canManageUsers(undefined)).toBe(false)
  })
})
