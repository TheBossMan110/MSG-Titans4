import type { Metadata } from 'next'
import { MarketingNav } from '@/components/layout/marketing-nav'
import { Footer } from '@/components/layout/footer'
import { PricingView } from '@/components/pricing/pricing-view'

export const metadata: Metadata = {
  title: 'Pricing',
  description: 'Plans for support teams in Pakistan, with AI complaint analysis that is checked against your own rules. Free 14-day trial.',
}

export default function PricingPage() {
  return (
    <>
      <MarketingNav />
      <main>
        <PricingView />
      </main>
      <Footer />
    </>
  )
}
