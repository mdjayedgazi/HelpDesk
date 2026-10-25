import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { ApiError } from '../lib/api.ts'
import { ProtectedLayout, RoleGate } from './guards.tsx'

const { useAuthMock, useMeMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  useMeMock: vi.fn(),
}))

vi.mock('@clerk/react', () => ({ useAuth: useAuthMock }))
vi.mock('../hooks/useMe.ts', () => ({ useMe: useMeMock }))
vi.mock('../components/AppShell.tsx', () => ({
  AppShell: ({ me }: { me: { username: string } }) => (
    <div>app-shell:{me.username}</div>
  ),
  FullPageLoading: () => <div>full-page-loading</div>,
}))
vi.mock('../components/StateViews.tsx', () => ({
  AccessDenied: ({ title = 'Access denied' }: { title?: string }) => (
    <div>access-denied:{title}</div>
  ),
  ErrorState: ({ title }: { title: string }) => <div>error-state:{title}</div>,
}))

function meResult(overrides: Record<string, unknown> = {}) {
  return {
    isPending: false,
    isError: false,
    error: null,
    data: {
      id: 'user-1',
      full_name: 'Test User',
      username: 'tester',
      email: 'tester@example.com',
      role: 'customer',
      is_active: true,
      image_url: null,
      created_at: '2026-10-23T00:00:00Z',
      updated_at: '2026-10-23T00:00:00Z',
    },
    refetch: vi.fn(),
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path='/sign-in' element={<div>sign-in-page</div>} />
        <Route path='/dashboard' element={<ProtectedLayout />} />
        <Route
          path='/gated'
          element={
            <RoleGate allow={['admin']}>
              <div>admin-content</div>
            </RoleGate>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: true })
  useMeMock.mockReturnValue(meResult())
})

describe('ProtectedLayout', () => {
  it('waits for Clerk before deciding anything', () => {
    useAuthMock.mockReturnValue({ isLoaded: false, isSignedIn: false })
    renderAt('/dashboard')
    expect(screen.getByText('full-page-loading')).toBeInTheDocument()
  })

  it('redirects signed-out visitors to sign-in', () => {
    useAuthMock.mockReturnValue({ isLoaded: true, isSignedIn: false })
    renderAt('/dashboard')
    expect(screen.getByText('sign-in-page')).toBeInTheDocument()
  })

  it('waits for the local profile before rendering the shell', () => {
    useMeMock.mockReturnValue(meResult({ isPending: true, data: undefined }))
    renderAt('/dashboard')
    expect(screen.getByText('full-page-loading')).toBeInTheDocument()
  })

  it('renders the application shell for an authorized profile', () => {
    renderAt('/dashboard')
    expect(screen.getByText('app-shell:tester')).toBeInTheDocument()
  })

  it('explains a 403 profile failure instead of retrying forever', () => {
    useMeMock.mockReturnValue(
      meResult({ isError: true, data: undefined, error: new ApiError(403, 'Inactive') }),
    )
    renderAt('/dashboard')
    expect(screen.getByText('access-denied:Account unavailable')).toBeInTheDocument()
  })

  it('redirects a 401 profile failure to sign-in', () => {
    useMeMock.mockReturnValue(
      meResult({ isError: true, data: undefined, error: new ApiError(401, 'No session') }),
    )
    renderAt('/dashboard')
    expect(screen.getByText('sign-in-page')).toBeInTheDocument()
  })
})

describe('RoleGate', () => {
  it('blocks a customer from an admin-only route', () => {
    renderAt('/gated')
    expect(screen.getByText(/access-denied/)).toBeInTheDocument()
    expect(screen.queryByText('admin-content')).not.toBeInTheDocument()
  })

  it('allows an admin into an admin-only route', () => {
    useMeMock.mockReturnValue(meResult({ data: { ...meResult().data, role: 'admin' } }))
    renderAt('/gated')
    expect(screen.getByText('admin-content')).toBeInTheDocument()
  })

  it('fails closed when no profile is available', () => {
    useMeMock.mockReturnValue(meResult({ isPending: false, data: undefined }))
    renderAt('/gated')
    expect(screen.getByText(/access-denied/)).toBeInTheDocument()
  })
})
