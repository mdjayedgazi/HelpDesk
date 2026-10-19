import { SignIn, useAuth } from '@clerk/react'
import { Navigate } from 'react-router-dom'

import { FullPageLoading } from '../../components/AppShell.tsx'
import { clerkAppearance } from './clerkAppearance.ts'
import { AuthLayout } from './AuthLayout.tsx'

export function SignInPage() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <FullPageLoading />
  if (isSignedIn) return <Navigate to='/dashboard' replace />

  return (
    <AuthLayout>
      <SignIn
        routing='path'
        path='/sign-in'
        signUpUrl='/sign-up'
        fallbackRedirectUrl='/dashboard'
        appearance={clerkAppearance}
      />
    </AuthLayout>
  )
}
