/**
 * Test-only Clerk stand-in used by the browser harness (`vite.harness.config.ts`).
 *
 * The harness renders the REAL application (routes, guards, pages, components,
 * React Query, Chakra) against fixture HTTP responses, but with authentication
 * short-circuited to a signed-in user. This lets us drive authenticated screens
 * and the responsive matrix in a real browser without a production identity.
 *
 * This module must NEVER be imported by application code or the production
 * build. It is reachable only through the harness Vite config's `@clerk/react`
 * alias, so the shipped bundle is unaffected. It deliberately implements only
 * the members the app uses.
 */
import type { ReactNode } from 'react'

interface StubUser {
  fullName: string
  imageUrl: string | null
  primaryEmailAddress: { emailAddress: string } | null
  setProfileImage: (args: { file: File }) => Promise<void>
}

const stubUser: StubUser = {
  fullName: 'Harness User',
  imageUrl: null,
  primaryEmailAddress: { emailAddress: 'harness@example.test' },
  setProfileImage: async () => {},
}

export function ClerkProvider({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export function useAuth() {
  return {
    isLoaded: true,
    isSignedIn: true,
    getToken: async () => 'harness-token',
    signOut: async () => {},
  }
}

export function useUser() {
  return { isLoaded: true, isSignedIn: true, user: stubUser }
}

export function useClerk() {
  return { signOut: async () => {} }
}

export function SignIn() {
  return <div data-harness='sign-in' />
}

export function SignUp() {
  return <div data-harness='sign-up' />
}
