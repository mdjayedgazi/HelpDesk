import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { usePrefetchTicketPage, useTickets } from './useTickets.ts'
import { queryKeys } from '../lib/queryKeys.ts'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))

vi.mock('../lib/useApi.ts', () => ({
  useApi: () => ({ request: requestMock, url: (p: string) => p }),
}))

function page(page: number, total: number) {
  return {
    items: [],
    total,
    page,
    page_size: 20,
    total_pages: Math.max(1, Math.ceil(total / 20)),
    has_next: page < Math.ceil(total / 20),
    has_previous: page > 1,
  }
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

beforeEach(() => {
  requestMock.mockReset()
  requestMock.mockImplementation((_path: string, opts: { query?: { page?: number } }) => {
    const requested = opts?.query?.page ?? 1
    return Promise.resolve(page(requested, 100))
  })
})

describe('usePrefetchTicketPage', () => {
  it('prefetches an uncached page into the same query key the list uses', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePrefetchTicketPage({ page: 1, page_size: 20 }), {
      wrapper: wrapper(client),
    })

    result.current(2)

    await waitFor(() => {
      const cached = client.getQueryData(
        queryKeys.tickets.list({ page: 2, page_size: 20 }),
      )
      expect(cached).toBeDefined()
    })
    // The prefetch used the ticket list endpoint exactly once for page 2.
    expect(requestMock).toHaveBeenCalledWith(
      expect.stringContaining('/tickets'),
      expect.objectContaining({ query: expect.objectContaining({ page: 2 }) }),
    )
  })

  it('does not refetch a page that is already cached', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const key = queryKeys.tickets.list({ page: 2, page_size: 20 })
    client.setQueryData(key, page(2, 100))

    const { result } = renderHook(() => usePrefetchTicketPage({ page: 1, page_size: 20 }), {
      wrapper: wrapper(client),
    })
    result.current(2)

    // Give any stray fetch a tick; none should occur.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(requestMock).not.toHaveBeenCalled()
  })

  it('is a no-op when params are undefined', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePrefetchTicketPage(undefined), {
      wrapper: wrapper(client),
    })
    result.current(2)
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(requestMock).not.toHaveBeenCalled()
  })
})

describe('useTickets caching', () => {
  it('exposes previous page data while the next page loads (keepPreviousData)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result, rerender } = renderHook(
      ({ pageNo }: { pageNo: number }) => useTickets({ page: pageNo, page_size: 20 }),
      { wrapper: wrapper(client), initialProps: { pageNo: 1 } },
    )
    await waitFor(() => expect(result.current.data?.page).toBe(1))

    // While page 2 resolves, the hook keeps the page-1 data as placeholder.
    rerender({ pageNo: 2 })
    // Immediately after the key change the placeholder is the previous page.
    expect(result.current.data?.page).toBe(1)
    await waitFor(() => expect(result.current.data?.page).toBe(2))
  })
})
