import { Component, type ErrorInfo, type ReactNode } from 'react'

import { palette } from '../theme/palette.ts'

interface ErrorBoundaryProps {
  children: ReactNode
  /** Optional custom fallback; receives the reset callback. */
  fallback?: (reset: () => void) => ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

/**
 * Application-level React error boundary.
 *
 * A render error anywhere below this boundary (for example a malformed
 * optimistic cache entry) would otherwise unmount the whole tree and show a
 * blank page. The boundary contains the failure, shows a useful fallback, and
 * lets the user recover without a hard reload. It deliberately logs only the
 * error to the console — never tokens, request bodies, or other user data.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the console useful for debugging without surfacing raw server
    // payloads in the UI. The stack is a developer aid, not user facing.
    console.error('Unhandled UI error', error, info.componentStack)
  }

  private readonly reset = (): void => {
    this.setState({ hasError: false })
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    if (this.props.fallback) return this.props.fallback(this.reset)

    return (
      <div
        role='alert'
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          background: palette.page,
          color: palette.text,
          textAlign: 'center',
        }}
      >
        <div style={{ maxWidth: '28rem' }}>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 500, margin: 0 }}>
            Something went wrong
          </h1>
          <p
            style={{
              marginTop: '0.75rem',
              fontSize: '0.875rem',
              color: palette.textSecondary,
            }}
          >
            This page ran into an unexpected problem. You can try again, or
            reload the application.
          </p>
          <div
            style={{
              marginTop: '1.25rem',
              display: 'flex',
              gap: '0.5rem',
              justifyContent: 'center',
            }}
          >
            <button
              type='button'
              onClick={this.reset}
              style={{
                padding: '0.5rem 1rem',
                fontSize: '0.875rem',
                border: `1px solid ${palette.border}`,
                borderRadius: '0.5rem',
                background: palette.surface,
                color: palette.text,
                cursor: 'pointer',
              }}
            >
              Try again
            </button>
            <button
              type='button'
              onClick={() => window.location.reload()}
              style={{
                padding: '0.5rem 1rem',
                fontSize: '0.875rem',
                border: `1px solid ${palette.border}`,
                borderRadius: '0.5rem',
                background: palette.ink,
                color: palette.textOnInk,
                cursor: 'pointer',
              }}
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    )
  }
}
