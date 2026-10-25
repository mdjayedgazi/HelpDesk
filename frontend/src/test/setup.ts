import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vite-plus/test'

// Vitest's `globals` mode is deliberately not enabled; register cleanup
// explicitly so each test starts with an empty DOM.
afterEach(cleanup)
