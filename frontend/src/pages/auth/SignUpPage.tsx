import { SignUp, useAuth } from '@clerk/react'
import { Navigate } from 'react-router-dom'

import { FullPageLoading } from '../../components/AppShell.tsx'
import { clerkAppearance } from './clerkAppearance.ts'
import { AuthLayout } from './AuthLayout.tsx'

export function SignUpPage() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <FullPageLoading />
  if (isSignedIn) return <Navigate to='/dashboard' replace />

  return (
    <AuthLayout>
      <SignUp
        routing='path'
        path='/sign-up'
        signInUrl='/sign-in'
        fallbackRedirectUrl='/dashboard'
        appearance={clerkAppearance}
      />
    </AuthLayout>
  )
}
