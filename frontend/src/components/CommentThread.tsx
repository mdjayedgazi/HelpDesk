import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { Lock } from 'lucide-react'

import { formatDateTime } from '../lib/format.ts'
import type { Comment, Role, StaffComment } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { UserAvatar } from './UserAvatar.tsx'

function isInternal(comment: Comment | StaffComment): comment is StaffComment {
  return 'is_internal' in comment && comment.is_internal
}

/**
 * The ticket conversation.
 *
 * Public replies and internal notes must never be confused at a glance, so an
 * internal note gets three independent signals: a lock icon, an explicit
 * "Internal note" label and a tinted, inset surface. The customer thread never
 * receives internal notes from the API, so this styling is staff-only in
 * practice but safe either way.
 */
export function CommentThread({
  comments,
  viewerId,
  viewerRole,
  userLabel,
  userImage,
}: {
  comments: Array<Comment | StaffComment>
  viewerId: string
  viewerRole: Role
  userLabel: (id: string) => string
  userImage?: (id: string) => string | null | undefined
}) {
  return (
    <Stack gap='0'>
      {comments.map((comment, index) => {
        const internal = isInternal(comment)
        const isOwn = comment.author_user_id === viewerId
        const authorName =
          viewerRole === 'customer' && !isOwn ? 'Support team' : userLabel(comment.author_user_id)

        return (
          <Flex
            key={comment.id}
            gap='3.5'
            py='5'
            px={internal ? '3.5' : '0'}
            my={internal ? '1' : '0'}
            borderTopWidth={index === 0 ? '0' : '1px'}
            borderTopColor={internal ? 'transparent' : palette.borderSubtle}
            bg={internal ? palette.surfaceMuted : 'transparent'}
            borderLeftWidth={internal ? '2px' : '0'}
            borderLeftColor={palette.borderStrong}
            borderRadius={internal ? 'l2' : '0'}
          >
            <UserAvatar
              name={authorName}
              src={userImage?.(comment.author_user_id)}
              tone={isOwn ? 'ink' : 'neutral'}
            />
            <Box flex='1' minW='0'>
              <Flex align='center' gap='2' wrap='wrap'>
                <Text fontSize='sm' fontWeight='semibold' color={palette.text}>
                  {authorName}
                </Text>
                {isOwn ? (
                  <Text fontSize='2xs' color={palette.textFaint}>
                    you
                  </Text>
                ) : null}
                <Text fontSize='xs' color={palette.textFaint}>
                  {formatDateTime(comment.created_at)}
                </Text>
                {internal ? (
                  <Flex
                    align='center'
                    gap='1'
                    px='1.5'
                    py='0.5'
                    borderRadius='full'
                    bg={palette.surface}
                    borderWidth='1px'
                    borderColor={palette.borderStrong}
                    color={palette.textSecondary}
                    title='Only the support team can see this note'
                  >
                    <Lock size={10} aria-hidden />
                    <Text fontSize='2xs' fontWeight='semibold' letterSpacing='0.02em'>
                      Internal note
                    </Text>
                  </Flex>
                ) : null}
              </Flex>
              <Text
                mt='1.5'
                fontSize='sm'
                color={palette.text}
                whiteSpace='pre-wrap'
                wordBreak='break-word'
                lineHeight='1.65'
              >
                {comment.body}
              </Text>
            </Box>
          </Flex>
        )
      })}
    </Stack>
  )
}
