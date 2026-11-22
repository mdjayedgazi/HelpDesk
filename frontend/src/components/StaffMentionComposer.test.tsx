import { ChakraProvider } from '@chakra-ui/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { StaffMentionComposer } from './StaffMentionComposer.tsx'
import { system } from '../theme/system.ts'
import type { User } from '../lib/types.ts'

const { useStaffDirectoryMock } = vi.hoisted(() => ({ useStaffDirectoryMock: vi.fn() }))
vi.mock('../hooks/useStaffMessages.ts', () => ({ useStaffDirectory: useStaffDirectoryMock }))

const alice: User = {
  id: 'u-alice',
  full_name: 'Alice Chen',
  username: 'alice',
  email: 'alice@example.com',
  role: 'agent',
  is_active: true,
  image_url: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
const alex: User = { ...alice, id: 'u-alex', full_name: 'Alex Morgan', username: 'alex', role: 'admin' }

function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return rtlRender(
    <ChakraProvider value={system}>
      <QueryClientProvider client={client}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>,
  )
}

function typeInto(textarea: HTMLTextAreaElement, value: string, caret = value.length) {
  fireEvent.change(textarea, { target: { value } })
  textarea.setSelectionRange(caret, caret)
  // Trigger the caret sync the component uses on click/keyup.
  fireEvent.click(textarea)
}

beforeEach(() => {
  useStaffDirectoryMock.mockReset()
  useStaffDirectoryMock.mockReturnValue({
    data: [alice, alex],
    isPending: false,
    isError: false,
  })
})

describe('StaffMentionComposer', () => {
  it('opens suggestions when the user types @', async () => {
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@')
    await waitFor(() => {
      expect(screen.getByRole('listbox', { name: 'Employee suggestions' })).toBeInTheDocument()
      expect(screen.getByText('Alice Chen')).toBeInTheDocument()
    })
  })

  it('passes the typed query to the directory (case preserved; search is CI)', async () => {
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@A')
    await waitFor(() => {
      const lastCall = useStaffDirectoryMock.mock.calls.at(-1)![0]
      expect(lastQuery(lastCall)).toBe('A')
    })
  })

  it('selects an employee and inserts @username plus the real id', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<StaffMentionComposer onSubmit={onSubmit} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@Ali')

    const option = await screen.findByRole('option', { name: /Alice Chen/ })
    fireEvent.click(option)

    await waitFor(() => {
      expect(textarea.value).toBe('@alice ')
    })

    // The chip confirms the structured selection.
    expect(screen.getByText('@alice', { selector: 'div' })).toBeInTheDocument()

    // Sending carries the real id, not the display name.
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        body: '@alice',
        mentionedUserIds: ['u-alice'],
      })
    })
  })

  it('supports two mentions in one message', async () => {
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement

    typeInto(textarea, '@')
    fireEvent.click(await screen.findByRole('option', { name: /Alice Chen/ }))
    await waitFor(() => expect(textarea.value).toBe('@alice '))

    typeInto(textarea, '@alice and @')
    fireEvent.click(await screen.findByRole('option', { name: /Alex Morgan/ }))
    await waitFor(() => expect(textarea.value).toBe('@alice and @alex '))
  })

  it('ArrowDown + Enter selects the highlighted employee instead of sending', async () => {
    const onSubmit = vi.fn()
    render(<StaffMentionComposer onSubmit={onSubmit} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@')

    await screen.findByRole('option', { name: /Alice Chen/ })
    fireEvent.keyDown(textarea, { key: 'ArrowDown' })
    fireEvent.keyDown(textarea, { key: 'Enter' })

    await waitFor(() => {
      // Enter picked Alex (second option), it did not send.
      expect(onSubmit).not.toHaveBeenCalled()
      expect(textarea.value).toBe('@alex ')
    })
  })

  it('Escape closes the suggestion panel', async () => {
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@')
    await screen.findByRole('listbox')

    fireEvent.keyDown(textarea, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  it('shows an empty state when nothing matches', async () => {
    useStaffDirectoryMock.mockReturnValue({ data: [], isPending: false, isError: false })
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@zzz')
    await waitFor(() => {
      expect(screen.getByText(/No active employee matches/i)).toBeInTheDocument()
    })
  })

  it('shows a loading state while the directory request is pending', async () => {
    useStaffDirectoryMock.mockReturnValue({ data: [], isPending: true, isError: false })
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@')
    await waitFor(() => {
      expect(screen.getByText('Searching…')).toBeInTheDocument()
    })
  })

  it('shows an error state when the lookup fails', async () => {
    useStaffDirectoryMock.mockReturnValue({ data: [], isPending: false, isError: true })
    render(<StaffMentionComposer onSubmit={vi.fn()} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement
    typeInto(textarea, '@')
    await waitFor(() => {
      expect(screen.getByText(/Could not load employees/i)).toBeInTheDocument()
    })
  })

  it('drops a mention from the payload when its text is removed', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<StaffMentionComposer onSubmit={onSubmit} />)
    const textarea = screen.getByRole('combobox') as HTMLTextAreaElement

    typeInto(textarea, '@')
    fireEvent.click(await screen.findByRole('option', { name: /Alice Chen/ }))
    await waitFor(() => expect(textarea.value).toBe('@alice '))

    // Remove the mention text entirely, then type and send a plain message.
    typeInto(textarea, 'plain message')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ body: 'plain message', mentionedUserIds: [] })
    })
  })
})

function lastQuery(call: { q?: string } | undefined): string | undefined {
  return call?.q
}
