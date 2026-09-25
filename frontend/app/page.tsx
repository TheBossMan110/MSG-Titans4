import { MarketingNav } from '@/components/layout/marketing-nav'
import { Footer } from '@/components/layout/footer'
import { Hero } from '@/components/landing/hero'
import { Ticker } from '@/components/landing/ticker'
import { Trust, Dimensions, Understanding, Pipeline } from '@/components/landing/sections-a'
import { PencilToInk, KnowledgeBase, Routing, Security } from '@/components/landing/sections-b'
import { LiveDemo, Analytics, HumanReview, Workflow, FinalCTA } from '@/components/landing/sections-c'

export default function LandingPage() {
  return (
    <>
      <MarketingNav />
      <main>
        <Hero />
        <Ticker />
        <Trust />
        <Dimensions />
        <Understanding />
        <Pipeline />
        <PencilToInk />
        <KnowledgeBase />
        <Routing />
        <Security />
        <LiveDemo />
        <Analytics />
        <HumanReview />
        <Workflow />
        <FinalCTA />
      </main>
      <Footer />
    </>
  )
}
