import { Box, Flex, Input, InputGroup, NativeSelect, Table, Text } from '@chakra-ui/react'
import { Search, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [active, setActive] = useState<'' | 'active' | 'inactive'>('')

  const debouncedSearch = useDebounced(search)

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, role, active])

  const users = useAdminUsers({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    q: debouncedSearch || undefined,
    role: role || undefined,
    is_active: active === '' ? undefined : active === 'active',
  })

  const items = users.data ?? []
  const hasNext = items.length === PAGE_SIZE

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
              itemCount={items.length}
              hasNext={hasNext}
              onPageChange={setPage}
            />
          </Box>
        </>
      )}
    </>
  )
}
