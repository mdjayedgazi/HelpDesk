import { ChakraProvider } from '@chakra-ui/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'

import { App } from './App.tsx'
import { Toaster } from './components/Toaster.tsx'
import { queryClient } from './lib/queryClient.ts'
import { ThemeProvider } from './theme/colorMode.tsx'
import { system } from './theme/system.ts'
import './index.css'
import { installFixtureFetch } from './harness-fixtures.ts'

installFixtureFetch()

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ChakraProvider value={system}>
        <ThemeProvider>
          <MemoryRouter initialEntries={[new URLSearchParams(location.search).get('route') ?? '/dashboard']}>
            <App />
            <Toaster />
          </MemoryRouter>
        </ThemeProvider>
      </ChakraProvider>
    </QueryClientProvider>
  </StrictMode>,
)
