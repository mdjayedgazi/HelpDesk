import { Box, Flex, Input, InputGroup, NativeSelect, Table, Text } from '@chakra-ui/react'
import { Search, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader.tsx'
import { Pagination } from '../../components/Pagination.tsx'
import { EmptyState, ErrorState, TableSkeleton } from '../../components/StateViews.tsx'
import { Surface } from '../../components/Surface.tsx'
import { ActiveStatusBadge, RoleBadge } from '../../components/badges.tsx'
import { UserAvatar } from '../../components/UserAvatar.tsx'
import { TicketTableSurface } from '../../components/TicketTable.tsx'
import { useAdminUsers } from '../../hooks/useAdmin.ts'
import { useDebounced } from '../../hooks/useDebounced.ts'
import { errorMessage } from '../../lib/errors.ts'
import { formatDate, roleLabels } from '../../lib/format.ts'
import { ALL_ROLES, type Role } from '../../lib/types.ts'
import { palette } from '../../theme/palette.ts'

const PAGE_SIZE = 20

export function AdminUsersPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const initialRole = searchParams.get('role') ?? ''
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<Role | ''>(
    ALL_ROLES.includes(initialRole as Role) ? (initialRole as Role) : '',
  )
  const [active, setActive] = useState<'' | 'active' | 'inactive'>(
    searchParams.get('active') === 'inactive'
      ? 'inactive'
      : searchParams.get('active') === 'active'
        ? 'active'
        : '',
  )

  // Keep the URL in sync so the dashboard can deep-link to a filtered directory
  // (for example `/admin/users?role=agent`) and the view can be shared. Only the
  // params this page owns are touched, and nothing is written when unchanged.
  useEffect(() => {
    if ((searchParams.get('role') ?? '') === role && (searchParams.get('active') ?? '') === active) {
      return
    }
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (role) next.set('role', role)
      else next.delete('role')
      if (active) next.set('active', active)
      else next.delete('active')
      return next
    }, { replace: true })
  }, [role, active, searchParams, setSearchParams])

  const debouncedSearch = useDebounced(search)

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, role, active])

  const users = useAdminUsers({
    page,
    page_size: PAGE_SIZE,
    q: debouncedSearch || undefined,
    role: role || undefined,
    is_active: active === '' ? undefined : active === 'active',
  })

  const pageData = users.data
  const items = pageData?.items ?? []

  // Reconcile the requested page with the server's truth. If users were removed
  // (or a filter shrank the set) while the viewer was on a high page, snap back
  // to the last valid page instead of showing an empty "page N". The server
  // envelope's `total_pages` is authoritative.
  useEffect(() => {
    if (!pageData) return
    const lastValid = Math.max(1, pageData.total_pages)
    if (page > lastValid) setPage(lastValid)
  }, [pageData, page])

  const selectStyles = {
    bg: palette.surface,
    borderColor: palette.border,
    borderRadius: 'l2',
    fontSize: 'sm',
    height: '9',
    _hover: { borderColor: palette.borderStrong },
    _focus: { borderColor: palette.ink },
  } as const

  return (
    <>
      <PageHeader
        title='Users'
        description='Manage accounts, roles and access across the help desk.'
      />

      <Flex gap='2.5' wrap='wrap' align='center' mb='5'>
        <InputGroup
          startElement={<Search size={15} color={palette.textMuted} aria-hidden />}
          maxW={{ base: 'full', sm: '72' }}
          flex={{ base: '1 1 100%', sm: '0 1 auto' }}
        >
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder='Search by name, username or email'
            aria-label='Search users'
            {...selectStyles}
            ps='8'
          />
        </InputGroup>

        <NativeSelect.Root size='sm' width='auto' minW='40'>
          <NativeSelect.Field
            value={role}
            onChange={(event) => setRole(event.target.value as Role | '')}
            aria-label='Filter by role'
            {...selectStyles}
          >
            <option value=''>All roles</option>
            {ALL_ROLES.map((value) => (
              <option key={value} value={value}>
                {roleLabels[value]}
              </option>
            ))}
          </NativeSelect.Field>
          <NativeSelect.Indicator color={palette.textMuted} />
        </NativeSelect.Root>

        <NativeSelect.Root size='sm' width='auto' minW='40'>
          <NativeSelect.Field
            value={active}
            onChange={(event) => setActive(event.target.value as '' | 'active' | 'inactive')}
            aria-label='Filter by account status'
            {...selectStyles}
          >
            <option value=''>All statuses</option>
            <option value='active'>Active</option>
            <option value='inactive'>Deactivated</option>
          </NativeSelect.Field>
          <NativeSelect.Indicator color={palette.textMuted} />
        </NativeSelect.Root>
      </Flex>

      {users.isPending ? (
        <Surface overflow='hidden'>
          <TableSkeleton rows={8} columns={4} />
        </Surface>
      ) : users.isError ? (
        <ErrorState
          title='Could not load users'
          description={errorMessage(users.error)}
          onRetry={() => void users.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Users}
          title='No users found'
          description='Try adjusting the search or filters.'
        />
      ) : (
        <>
          <TicketTableSurface>
            <Table.ScrollArea borderWidth='0'>
              <Table.Root size='sm' variant='line' interactive>
                <Table.Header>
                  <Table.Row bg={palette.surface}>
                    <Table.ColumnHeader color={palette.textMuted} fontSize='xs' fontWeight='medium'>
                      User
                    </Table.ColumnHeader>
                    <Table.ColumnHeader
                      color={palette.textMuted}
                      fontSize='xs'
                      fontWeight='medium'
                      display={{ base: 'none', lg: 'table-cell' }}
                    >
                      Email
                    </Table.ColumnHeader>
                    <Table.ColumnHeader color={palette.textMuted} fontSize='xs' fontWeight='medium'>
                      Role
                    </Table.ColumnHeader>
                    <Table.ColumnHeader color={palette.textMuted} fontSize='xs' fontWeight='medium'>
                      Status
                    </Table.ColumnHeader>
                    <Table.ColumnHeader
                      color={palette.textMuted}
                      fontSize='xs'
                      fontWeight='medium'
                      textAlign='right'
                      display={{ base: 'none', sm: 'table-cell' }}
                    >
                      Joined
                    </Table.ColumnHeader>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {items.map((user) => (
                    <Table.Row
                      key={user.id}
                      cursor='pointer'
                      transition='background 0.16s ease'
                      _hover={{ bg: palette.hover }}
                      onClick={() => navigate(`/admin/users/${user.id}`)}
                    >
                      <Table.Cell py='3.5'>
                        <Flex align='center' gap='3' minW='0'>
                          <UserAvatar name={user.full_name} size='sm' src={user.image_url} />
                          <Box minW='0'>
                            <Text fontSize='sm' fontWeight='medium' color={palette.text} truncate>
                              {user.full_name}
                            </Text>
                            <Text fontSize='xs' color={palette.textMuted} truncate>
                              @{user.username}
                            </Text>
                          </Box>
                        </Flex>
                      </Table.Cell>
                      <Table.Cell
                        display={{ base: 'none', lg: 'table-cell' }}
                        fontSize='sm'
                        color={palette.textSecondary}
                      >
                        {user.email}
                      </Table.Cell>
                      <Table.Cell>
                        <RoleBadge role={user.role} />
                      </Table.Cell>
                      <Table.Cell>
                        <ActiveStatusBadge isActive={user.is_active} />
                      </Table.Cell>
                      <Table.Cell
                        display={{ base: 'none', sm: 'table-cell' }}
                        textAlign='right'
                        fontSize='xs'
                        color={palette.textMuted}
                        whiteSpace='nowrap'
                      >
                        {formatDate(user.created_at)}
                      </Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Root>
            </Table.ScrollArea>
          </TicketTableSurface>
          <Box mt='4'>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={pageData?.total ?? 0}
              totalPages={pageData?.total_pages ?? 1}
              isLoading={users.isFetching}
              onPageChange={setPage}
            />
          </Box>
        </>
      )}
    </>
  )
}
