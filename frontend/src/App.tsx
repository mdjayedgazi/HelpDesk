import { Route, Routes } from 'react-router-dom'

import { ProtectedLayout, RoleGate } from './auth/guards.tsx'
import { DashboardPage } from './pages/DashboardPage.tsx'
import { NewTicketPage } from './pages/NewTicketPage.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { NotificationsPage } from './pages/NotificationsPage.tsx'
import { ProfilePage } from './pages/ProfilePage.tsx'
import { TicketDetailPage } from './pages/TicketDetailPage.tsx'
import { TicketsPage } from './pages/TicketsPage.tsx'
import { AdminDashboard } from './pages/admin/AdminDashboard.tsx'
import { AdminUserDetailPage } from './pages/admin/AdminUserDetailPage.tsx'
import { AdminUsersPage } from './pages/admin/AdminUsersPage.tsx'
import { AgentQueuePage } from './pages/agent/AgentQueuePage.tsx'
import { SignInPage } from './pages/auth/SignInPage.tsx'
import { SignUpPage } from './pages/auth/SignUpPage.tsx'
import { HomePage } from './pages/marketing/HomePage.tsx'
import { AccountRequestDetailPage } from './pages/staff/AccountRequestDetailPage.tsx'
import { AccountRequestsPage } from './pages/staff/AccountRequestsPage.tsx'
import { MessagesPage } from './pages/staff/MessagesPage.tsx'

export function App() {
  return (
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
  )
}
