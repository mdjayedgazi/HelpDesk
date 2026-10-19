import { useAuth } from '@clerk/react'
import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { AppShell, FullPageLoading } from '../components/AppShell.tsx'
import { AccessDenied, ErrorState } from '../components/StateViews.tsx'
import { useMe } from '../hooks/useMe.ts'
import { ApiError } from '../lib/api.ts'
import { errorMessage } from '../lib/errors.ts'
import type { Role } from '../lib/types.ts'

/**
 * Gate for the authenticated application.
 *
 * Authentication comes from Clerk; *authorization* comes from the application
 * role on the profile returned by the backend (`/api/v1/users/me`). We never
 * trust client-side role hints.
 */
export function ProtectedLayout() {
  const { isLoaded, isSignedIn } = useAuth()
  const location = useLocation()
  const me = useMe()

  if (!isLoaded) return <FullPageLoading />

  if (!isSignedIn) {
    return <Navigate to='/sign-in' replace state={{ from: location.pathname }} />
  }

  if (me.isPending) return <FullPageLoading />

  if (me.isError) {
    const error = me.error
    if (error instanceof ApiError && error.status === 401) {
      return <Navigate to='/sign-in' replace />
    }
    if (error instanceof ApiError && error.status === 403) {
      return <AccessDenied title='Account unavailable' description={error.message} />
    }
    return (
      <ErrorState
        title='Could not load your profile'
        description={errorMessage(error)}
        onRetry={() => void me.refetch()}
      />
    )
  }

  if (!me.data) return <FullPageLoading />

  return <AppShell me={me.data} />
}

/**
 * Restricts a route subtree to a set of application roles.
 *
 * This is a UX guard only. The backend independently enforces every
 * permission, so bypassing it client-side would still be rejected by the API.
 */
export function RoleGate({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const me = useMe()

  if (me.isPending) return <FullPageLoading />
  if (!me.data) return <AccessDenied />

  if (!allow.includes(me.data.role)) {
    return <AccessDenied description={`This area is available to ${allow.join(', ')} accounts.`} />
  }

  return <>{children}</>
}

/** Convenience wrapper that renders an `<Outlet/>` for role-restricted routes. */
export function RoleOutlet({ allow }: { allow: Role[] }) {
  return (
    <RoleGate allow={allow}>
      <Outlet />
    </RoleGate>
  )
}
