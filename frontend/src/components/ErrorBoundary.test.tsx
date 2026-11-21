import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

import { ErrorBoundary } from './ErrorBoundary.tsx'

function Boom(): never {
  throw new Error('simulated render failure')
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ErrorBoundary', () => {
  it('renders a useful fallback instead of a blank page', () => {
    // React logs the caught error; silence it so the test output stays clean.
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  })

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <div>safe content</div>
      </ErrorBoundary>,
    )

    expect(screen.getByText('safe content')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('calls a custom fallback with a working reset callback', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    let showBoom = true
    function Toggle() {
      if (showBoom) throw new Error('boom')
      return <div>recovered</div>
    }

    render(
      <ErrorBoundary
        fallback={(reset) => (
          <button
            type='button'
            onClick={() => {
              showBoom = false
              reset()
            }}
          >
            recover
          </button>
        )}
      >
        <Toggle />
      </ErrorBoundary>,
    )

    const button = screen.getByRole('button', { name: 'recover' })
    button.click()

    // React re-renders the subtree after the boundary resets.
    expect(await screen.findByText('recovered')).toBeInTheDocument()
  })
})
