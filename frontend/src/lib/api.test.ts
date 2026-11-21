import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

import {
  ApiError,
  createApiClient,
  DEFAULT_REQUEST_TIMEOUT_MS,
  DEFAULT_UPLOAD_TIMEOUT_MS,
} from './api.ts'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const getToken = async () => 'session-token'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('createApiClient request timeout', () => {
  it('aborts a request that exceeds the default timeout', async () => {
    vi.useFakeTimers()
    // A fetch that never resolves on its own; only the abort signal ends it.
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          if (init?.signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'))
            return
          }
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient(getToken)
    // Capture the rejection immediately so fake-timer advancement never
    // surfaces an unhandled rejection before the assertion attaches.
    const captured = client.request('/api/v1/users/me').then(
      () => null,
      (error: unknown) => error,
    )

    await vi.advanceTimersByTimeAsync(DEFAULT_REQUEST_TIMEOUT_MS + 1)

    const error = (await captured) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(0)
    expect(error.message).toContain('took too long')
  })

  it('uses the longer upload timeout for multipart requests', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    let settled = false
    const client = createApiClient(getToken)
    const pending = client
      .request('/api/v1/tickets/1/attachments', {
        method: 'POST',
        formData: new FormData(),
      })
      .then(
        () => null,
        (error: unknown) => error,
      )
    pending.then(() => {
      settled = true
    }, () => {
      settled = true
    })

    // Still pending after the normal timeout window...
    await vi.advanceTimersByTimeAsync(DEFAULT_REQUEST_TIMEOUT_MS + 1)
    expect(settled).toBe(false)

    // ...but rejected once the upload timeout elapses.
    await vi.advanceTimersByTimeAsync(DEFAULT_UPLOAD_TIMEOUT_MS)
    expect(await pending).toBeInstanceOf(ApiError)
  })

  it('does not start a timer when timeoutMs is 0', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ok: true })))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient(getToken)
    const result = await client.request<{ ok: boolean }>('/api/v1/users/me', {
      timeoutMs: 0,
    })

    expect(result).toEqual({ ok: true })
    // Advancing time must not abort a completed request.
    await vi.advanceTimersByTimeAsync(DEFAULT_REQUEST_TIMEOUT_MS * 2)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('propagates a caller cancellation as AbortError, not a timeout', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          if (init?.signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'))
            return
          }
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient(getToken)
    const pending = client.request('/api/v1/users/me', { signal: controller.signal })
    controller.abort()

    const error = (await pending.catch((caught) => caught)) as Error
    expect(error.name).toBe('AbortError')
  })

  it('does not leak the timeout into a successful request', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ok: true })))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient(getToken)
    const result = await client.request<{ ok: boolean }>('/api/v1/users/me')

    expect(result).toEqual({ ok: true })
    expect(vi.getTimerCount()).toBe(0)
  })
})
