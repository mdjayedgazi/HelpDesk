import { Box, Flex } from '@chakra-ui/react'

import { Container } from '../../components/Container.tsx'
import { CtaSection } from '../../components/marketing/CtaSection.tsx'
import { FeatureSection } from '../../components/marketing/FeatureSection.tsx'
import { HeroSection } from '../../components/marketing/HeroSection.tsx'
import { SecuritySection } from '../../components/marketing/SecuritySection.tsx'
import { ShowcaseSection } from '../../components/marketing/ShowcaseSection.tsx'
import { SiteFooter } from '../../components/marketing/SiteFooter.tsx'
import { SiteHeader } from '../../components/marketing/SiteHeader.tsx'
import { WorkflowSection } from '../../components/marketing/WorkflowSection.tsx'
import { palette } from '../../theme/palette.ts'

/**
 * Public marketing homepage.
 *
 * Rendered at `/` for everyone. Signed-in visitors are never redirected into
 * the workspace from here — they get an explicit "Open workspace" action in the
 * header and hero instead.
 */
export function HomePage() {
  return (
    <Flex direction='column' minH='100vh' bg={palette.page}>
      <SiteHeader />

      <Box as='main' flex='1'>
        <HeroSection />

        <Container size='wide'>
          <FeatureSection />
        </Container>

        <ShowcaseSection />

        <Container size='wide'>
          <WorkflowSection />
          <SecuritySection />
          <CtaSection />
        </Container>
      </Box>

      <SiteFooter />
    </Flex>
  )
}
