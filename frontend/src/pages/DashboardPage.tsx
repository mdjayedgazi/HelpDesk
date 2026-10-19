import { LoadingState } from '../components/StateViews.tsx'
import { useMe } from '../hooks/useMe.ts'
import { AdminDashboard } from './admin/AdminDashboard.tsx'
import { AgentDashboard } from './agent/AgentDashboard.tsx'
import { CustomerDashboard } from './customer/CustomerDashboard.tsx'

export function DashboardPage() {
  const me = useMe()

  if (me.isPending) return <LoadingState label='Loading your workspace…' />
  if (!me.data) return null

  switch (me.data.role) {
    case 'admin':
      return <AdminDashboard />
    // The Owner is a super-administrator: the same organization-wide metrics,
    // plus navigation to the Owner inbox and the account-request queue.
    case 'owner':
      return <AdminDashboard variant='owner' />
    case 'agent':
      return <AgentDashboard me={me.data} />
    default:
      return <CustomerDashboard me={me.data} />
  }
}
