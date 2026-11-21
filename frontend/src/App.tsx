import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'

import { FullPageLoading } from './components/AppShell.tsx'
import { ProtectedLayout, RoleGate } from './auth/guards.tsx'

/**
 * Route-level code splitting.
 *
 * The production bundle was a single ~1.2 MB chunk, so a first visit downloaded
 * every page (admin, staff messaging, account requests, ticket detail) before
 * rendering anything. Each page is now its own chunk, loaded on navigation.
 * The route tree, guards, and API contracts are unchanged; only the load timing
 * differs. `ProtectedLayout`/`RoleGate` stay eager because they gate every
 * authenticated route and are tiny.
 */
const HomePage = lazy(() =>
  import('./pages/marketing/HomePage.tsx').then((m) => ({ default: m.HomePage })),
)
const SignInPage = lazy(() =>
  import('./pages/auth/SignInPage.tsx').then((m) => ({ default: m.SignInPage })),
)
const SignUpPage = lazy(() =>
  import('./pages/auth/SignUpPage.tsx').then((m) => ({ default: m.SignUpPage })),
)
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage.tsx').then((m) => ({ default: m.DashboardPage })),
)
const TicketsPage = lazy(() =>
  import('./pages/TicketsPage.tsx').then((m) => ({ default: m.TicketsPage })),
)
const NewTicketPage = lazy(() =>
  import('./pages/NewTicketPage.tsx').then((m) => ({ default: m.NewTicketPage })),
)
const TicketDetailPage = lazy(() =>
  import('./pages/TicketDetailPage.tsx').then((m) => ({
    default: m.TicketDetailPage,
  })),
)
const NotFoundPage = lazy(() =>
  import('./pages/NotFoundPage.tsx').then((m) => ({ default: m.NotFoundPage })),
)
const NotificationsPage = lazy(() =>
  import('./pages/NotificationsPage.tsx').then((m) => ({
    default: m.NotificationsPage,
  })),
)
const ProfilePage = lazy(() =>
  import('./pages/ProfilePage.tsx').then((m) => ({ default: m.ProfilePage })),
)
const AdminDashboard = lazy(() =>
  import('./pages/admin/AdminDashboard.tsx').then((m) => ({
    default: m.AdminDashboard,
  })),
)
const AdminUserDetailPage = lazy(() =>
  import('./pages/admin/AdminUserDetailPage.tsx').then((m) => ({
    default: m.AdminUserDetailPage,
  })),
)
const AdminUsersPage = lazy(() =>
  import('./pages/admin/AdminUsersPage.tsx').then((m) => ({
    default: m.AdminUsersPage,
  })),
)
const AgentQueuePage = lazy(() =>
  import('./pages/agent/AgentQueuePage.tsx').then((m) => ({
    default: m.AgentQueuePage,
  })),
)
const AccountRequestDetailPage = lazy(() =>
  import('./pages/staff/AccountRequestDetailPage.tsx').then((m) => ({
    default: m.AccountRequestDetailPage,
  })),
)
const AccountRequestsPage = lazy(() =>
  import('./pages/staff/AccountRequestsPage.tsx').then((m) => ({
    default: m.AccountRequestsPage,
  })),
)
const MessagesPage = lazy(() =>
  import('./pages/staff/MessagesPage.tsx').then((m) => ({
    default: m.MessagesPage,
  })),
)

export function App() {
  return (
    <Suspense fallback={<FullPageLoading />}>
      <Routes>
        {/* Public marketing homepage. Authenticated visitors are *not* redirected
            away from here; they get an explicit workspace action instead. */}
        <Route path='/' element={<HomePage />} />
        <Route path='/sign-in/*' element={<SignInPage />} />
        <Route path='/sign-up/*' element={<SignUpPage />} />

        <Route element={<ProtectedLayout />}>
          <Route path='dashboard' element={<DashboardPage />} />
          <Route path='tickets' element={<TicketsPage />} />
          <Route
            path='tickets/new'
            element={
              <RoleGate allow={['customer']}>
                <NewTicketPage />
              </RoleGate>
            }
          />
          <Route path='tickets/:ticketId' element={<TicketDetailPage />} />
          {/* The agent queue is for AGENT users only. Admins manage tickets
              through the administrative views (/tickets, /admin). */}
          <Route
            path='queue'
            element={
              <RoleGate allow={['agent']}>
                <AgentQueuePage />
              </RoleGate>
            }
          />
          <Route path='notifications' element={<NotificationsPage />} />
          <Route path='profile' element={<ProfilePage />} />
          {/* Private staff channels. Customers are deliberately excluded: they
              have no access to staff messaging or account-managed escalations,
              and the backend rejects customer calls with 403 regardless. */}
          <Route
            path='messages'
            element={
              <RoleGate allow={['agent', 'admin', 'owner']}>
                <MessagesPage />
              </RoleGate>
            }
          />
          <Route
            path='account-requests'
            element={
              <RoleGate allow={['agent', 'admin', 'owner']}>
                <AccountRequestsPage />
              </RoleGate>
            }
          />
          <Route
            path='account-requests/:requestId'
            element={
              <RoleGate allow={['agent', 'admin', 'owner']}>
                <AccountRequestDetailPage />
              </RoleGate>
            }
          />
          <Route
            path='admin'
            element={
              <RoleGate allow={['admin', 'owner']}>
                <AdminDashboard />
              </RoleGate>
            }
          />
          <Route
            path='admin/users'
            element={
              <RoleGate allow={['admin', 'owner']}>
                <AdminUsersPage />
              </RoleGate>
            }
          />
          <Route
            path='admin/users/:userId'
            element={
              <RoleGate allow={['admin', 'owner']}>
                <AdminUserDetailPage />
              </RoleGate>
            }
          />
          <Route path='*' element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
