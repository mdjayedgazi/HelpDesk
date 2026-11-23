import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { AdminUsersPage } from './AdminUsersPage.tsx'
import { renderPage } from '../../test/renderPage.tsx'
import type { User, UserPage } from '../../lib/types.ts'

const { useAdminUsersMock } = vi.hoisted(() => ({
  useAdminUsersMock: vi.fn(),
}))

// The page only needs the directory hook; the user-directory display-name
// lookup is stubbed so the table can render without a second query.
vi.mock('../../hooks/useAdmin.ts', () => ({
  useAdminUsers: useAdminUsersMock,
}))

vi.mock('../../hooks/useUserDirectory.ts', () => ({
  useUserDirectory: () => ({
    isResolved: true,
    user: () => undefined,
    label: (id: string | null | undefined) => (id ? `User ${id}` : '—'),
  }),
}))

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    full_name: 'Avery Bennett',
    username: 'avery',
    email: 'avery@example.test',
    role: 'agent',
    is_active: true,
    image_url: null,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    ...overrides,
  }
}

function buildPage(overrides: Partial<UserPage> = {}): UserPage {
  return {
    items: [buildUser()],
    total: 1,
    page: 1,
    page_size: 20,
    total_pages: 1,
    has_next: false,
    has_previous: false,
    ...overrides,
  }
}

function queryResult(overrides: Record<string, unknown>) {
  return {
    data: undefined,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  }
}

describe('AdminUsersPage', () => {
  beforeEach(() => {
    useAdminUsersMock.mockReset()
  })

  it('does not show the empty state while the first page loads', () => {
    useAdminUsersMock.mockReturnValue(queryResult({ isPending: true }))
    renderPage(<AdminUsersPage />, { route: '/admin/users' })
    expect(screen.queryByText('No users found')).not.toBeInTheDocument()
  })

  it('renders users from the server envelope', () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({
        data: buildPage({
          items: [
            buildUser({ id: 'u1', full_name: 'Avery Bennett', username: 'avery' }),
            buildUser({
              id: 'u2',
              full_name: 'Blake Cruz',
              username: 'blake',
              role: 'admin',
              is_active: false,
            }),
          ],
          total: 2,
        }),
      }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })

    expect(screen.getByText('Avery Bennett')).toBeInTheDocument()
    expect(screen.getByText('Blake Cruz')).toBeInTheDocument()
    expect(screen.getByText('@avery')).toBeInTheDocument()
  })

  it('derives pagination from server metadata and requests the next page', async () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({
        data: buildPage({
          total: 45,
          total_pages: 3,
          has_next: true,
          has_previous: false,
        }),
      }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })

    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByText('45')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))

    await waitFor(() =>
      expect(useAdminUsersMock).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2, page_size: 20 }),
      ),
    )
  })

  it('runs Previous back to page 1', async () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({
        data: buildPage({
          total: 45,
          total_pages: 3,
          page: 2,
          has_next: true,
          has_previous: true,
        }),
      }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() =>
      expect(useAdminUsersMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
      ),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    await waitFor(() =>
      expect(useAdminUsersMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1 }),
      ),
    )
  })

  it('shows an empty state when the filtered set is empty', () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({ data: buildPage({ items: [], total: 0, total_pages: 1 }) }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })
    expect(screen.getByText('No users found')).toBeInTheDocument()
  })

  it('shows an error state', () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({ isError: true, error: new Error('boom'), refetch: vi.fn() }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })
    expect(screen.getByText('Could not load users')).toBeInTheDocument()
  })

  it('resets to page 1 when the search term changes', async () => {
    useAdminUsersMock.mockReturnValue(
      queryResult({ data: buildPage({ total: 45, total_pages: 3, has_next: true }) }),
    )
    renderPage(<AdminUsersPage />, { route: '/admin/users' })

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() =>
      expect(useAdminUsersMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
      ),
    )

    fireEvent.change(screen.getByLabelText('Search users'), {
      target: { value: 'blake' },
    })

    await waitFor(
      () =>
        expect(useAdminUsersMock).toHaveBeenLastCalledWith(
          expect.objectContaining({ page: 1, q: 'blake' }),
        ),
      { timeout: 2000 },
    )
  })
})
