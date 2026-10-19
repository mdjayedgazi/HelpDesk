import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import { Lock } from 'lucide-react'

import { formatDateTime } from '../lib/format.ts'
import type { Comment, Role, StaffComment } from '../lib/types.ts'
import { palette } from '../theme/palette.ts'
import { UserAvatar } from './UserAvatar.tsx'

function isInternal(comment: Comment | StaffComment): comment is StaffComment {
  return 'is_internal' in comment && comment.is_internal
}

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
            borderTopWidth={index === 0 ? '0' : '1px'}
            borderColor={palette.borderSubtle}
          >
            <UserAvatar
              name={authorName}
              src={userImage?.(comment.author_user_id)}
              tone={isOwn ? 'ink' : 'neutral'}
            />
            <Box flex='1' minW='0'>
              <Flex align='center' gap='2' wrap='wrap'>
                <Text fontSize='sm' fontWeight='medium' color={palette.text}>
                  {authorName}
                </Text>
                {isOwn ? (
                  <Text fontSize='2xs' color={palette.textFaint}>
                    author
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
                    borderWidth='1px'
                    borderColor={palette.borderStrong}
                    borderStyle='dashed'
                    color={palette.textSecondary}
                  >
                    <Lock size={10} aria-hidden />
                    <Text fontSize='2xs' fontWeight='medium'>
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
                lineHeight='1.6'
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
