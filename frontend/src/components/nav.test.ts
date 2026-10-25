import { describe, expect, it } from 'vite-plus/test'

import { navSectionsForRole, sectionTitleForPath } from './nav.ts'

function dashboardTarget(role: Parameters<typeof navSectionsForRole>[0]) {
  const sections = navSectionsForRole(role)
  const item = sections.flatMap((section) => section.items).find((entry) => entry.label === 'Dashboard')
  return item?.to
}

describe('role navigation', () => {
  it.each(['customer', 'agent', 'admin', 'owner'] as const)(
    'points the %s Dashboard entry at the authenticated dashboard',
    (role) => {
      expect(dashboardTarget(role)).toBe('/dashboard')
    },
  )

  it('keeps the marketing homepage out of the customer navigation', () => {
    const targets = navSectionsForRole('customer').flatMap((section) =>
      section.items.map((item) => item.to),
    )
    expect(targets).not.toContain('/')
    expect(targets).toContain('/tickets')
  })

  it('does not expose staff messaging to customers', () => {
    const labels = navSectionsForRole('customer').flatMap((section) =>
      section.items.map((item) => item.label),
    )
    expect(labels).not.toContain('Message Owner')
    expect(labels).toContain('My tickets')
  })

  it('gives admins the user-management destination and owner inbox label', () => {
    const ownerLabels = navSectionsForRole('owner').flatMap((section) =>
      section.items.map((item) => item.label),
    )
    const adminLabels = navSectionsForRole('admin').flatMap((section) =>
      section.items.map((item) => item.label),
    )
    expect(ownerLabels).toContain('Users')
    expect(ownerLabels).toContain('Owner inbox')
    expect(adminLabels).toContain('Users')
    expect(adminLabels).toContain('Message Owner')
  })
})

describe('sectionTitleForPath', () => {
  it('labels the authenticated dashboard correctly', () => {
    expect(sectionTitleForPath('/dashboard')).toBe('Dashboard')
    expect(sectionTitleForPath('/tickets/new')).toBe('New ticket')
    expect(sectionTitleForPath('/tickets/123')).toBe('Ticket')
  })
})
