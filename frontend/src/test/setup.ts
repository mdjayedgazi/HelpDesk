import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vite-plus/test'

// jsdom does not implement the browser APIs that Chakra UI / Zag widgets
// (Tabs, Select, Menu, ...) probe on mount. Provide inert, side-effect-free
// polyfills so component tests exercise the real widget instead of crashing.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

// Vitest's `globals` mode is deliberately not enabled; register cleanup
// explicitly so each test starts with an empty DOM.
afterEach(cleanup)
