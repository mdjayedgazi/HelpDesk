import { ChakraProvider } from '@chakra-ui/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'

import { system } from '../theme/system.ts'

/**
 * Test renderer for page-level components.
 *
 * Pages read Chakra's design system, React Query's cache and React Router's
 * location, so all three are provided here. Queries point at a client with
 * retries disabled so a failing hook surfaces immediately instead of waiting.
 */
export function renderPage(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </QueryClientProvider>
      </ChakraProvider>
    )
  }

  return render(ui, { wrapper: Wrapper })
}
