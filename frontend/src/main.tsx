import { Box, ChakraProvider, Code, Heading, Stack, Text } from '@chakra-ui/react'
import { ClerkProvider } from '@clerk/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App.tsx'
import { Toaster } from './components/Toaster.tsx'
import { queryClient } from './lib/queryClient.ts'
import { palette } from './theme/palette.ts'
import { system } from './theme/system.ts'
import './index.css'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

/**
 * Friendly, monochrome configuration notice shown when the Clerk key is missing.
 * Without it the entire auth flow cannot initialise, so failing loudly here is
 * far clearer than a blank screen.
 */
function MissingConfiguration() {
  return (
    <Box
      minH='100vh'
      display='flex'
      alignItems='center'
      justifyContent='center'
      p='8'
      bg={palette.page}
    >
      <Stack gap='4' maxW='lg'>
        <Heading as='h1' fontSize='2xl' fontWeight='medium' color={palette.text}>
          HelpDesk is not configured
        </Heading>
        <Text fontSize='sm' color={palette.textSecondary}>
          Set{' '}
          <Code bg={palette.inset} color={palette.text}>
            VITE_CLERK_PUBLISHABLE_KEY
          </Code>{' '}
          in your environment (for example in <Code bg={palette.inset}>frontend/.env</Code>), then
          restart the dev server.
        </Text>
      </Stack>
    </Box>
  )
}

function Root() {
  if (!publishableKey) return <MissingConfiguration />

  return (
    <ClerkProvider publishableKey={publishableKey} afterSignOutUrl='/'>
      <QueryClientProvider client={queryClient}>
        <ChakraProvider value={system}>
          <BrowserRouter>
            <App />
            <Toaster />
          </BrowserRouter>
        </ChakraProvider>
      </QueryClientProvider>
    </ClerkProvider>
  )
}

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
