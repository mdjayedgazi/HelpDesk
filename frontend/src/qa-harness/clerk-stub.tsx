/**
 * Temporary browser-QA Clerk stub.
 *
 * The real app is rendered through Vite with `@clerk/react` aliased to this
 * module so the isolated QA API harness can choose a seeded role. Never part
 * of a production build; deleted after verification.
 */
import type { ReactNode } from 'react'

const qaUser = {
  id: 'user_qa',
  fullName: 'QA User',
  firstName: 'QA',
  lastName: 'User',
  username: 'qa',
  imageUrl: '',
  primaryEmailAddress: { emailAddress: 'qa@example.test' },
  setProfileImage: async () => {},
}

export function ClerkProvider({
  children,
}: {
  children?: ReactNode
  [key: string]: unknown
}) {
  return <>{children}</>
}

export function useAuth() {
  return {
    isLoaded: true,
    isSignedIn: true,
    userId: 'user_qa',
    getToken: async () => null,
  }
}

export function useUser() {
  return { isLoaded: true, isSignedIn: true, user: qaUser }
}

export function useClerk() {
  return { signOut: async () => {} }
}

export function SignIn() {
  return null
}

export function SignUp() {
  return null
}
