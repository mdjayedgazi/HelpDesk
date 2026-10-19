import { Button } from '@chakra-ui/react'
import { Link } from 'react-router-dom'

import { EmptyState } from '../components/StateViews.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { palette } from '../theme/palette.ts'
import { FileQuestion } from 'lucide-react'

export function NotFoundPage() {
  return (
    <>
      <PageHeader title='Page not found' />
      <EmptyState
        icon={FileQuestion}
        title='We could not find that page'
        description='The link may be broken or the page may have moved.'
        action={
          <Button asChild size='sm' variant='outline' borderColor={palette.border}>
            <Link to='/dashboard'>Back to dashboard</Link>
          </Button>
        }
      />
    </>
  )
}
