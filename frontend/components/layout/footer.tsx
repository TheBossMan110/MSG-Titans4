import Link from 'next/link'
import { MotionToggle } from '@/components/ui/motion-toggle'
import { Wordmark } from '@/components/ui/primitives'

export function Footer() {
  return (
    <footer id="about" className="section-dark grain relative">
      <div className="container-x py-16 md:py-20">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Wordmark dark />
            <p className="mt-4 max-w-[38ch] text-[14px] leading-relaxed text-sand-2">
              Complaint intelligence with a second opinion. The AI proposes;
              the company’s own rules confirm. Nothing reaches a customer
              unverified.
            </p>
          </div>
          <FooterCol title="Product" items={[['#product', 'How it works'], ['#intelligence', 'The pipeline'], ['#security', 'Security'], ['#analytics', 'Analytics']]} />
          <FooterCol title="Application" items={[['/login', 'Sign in'], ['/track', 'Track a complaint'], ['/dashboard', 'Dashboard']]} />
          <FooterCol title="Evaluation" items={[['/dashboard/benchmark', 'Benchmark'], ['/dashboard/rules/sandbox', 'Rule sandbox'], ['/dashboard/security', 'Deliberate defects'], ['/dashboard/audit', 'Audit trail']]} />
        </div>
        <div className="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-ink-on-dark/15 pt-6 text-[12.5px] text-sand-2">
          <span>SupportNova · ResponseX Intelligence · TechWiz 7, Generative AI PowerPlay · Team MSG-Titans4</span>
          <span className="font-mono">RaftarXpress Logistics (Pvt) Ltd — fictional organisation</span>
          <MotionToggle dark />
        </div>
      </div>
    </footer>
  )
}

function FooterCol({ title, items }: { title: string; items: Array<[string, string]> }) {
  return (
    <div>
      <p className="eyebrow mb-4 text-sand-2">{title}</p>
      <ul className="flex flex-col gap-2.5 text-[14px]">
        {items.map(([href, label]) => (
          <li key={href}>
            <Link href={href} className="text-ink-on-dark/85 transition-colors hover:text-ink-on-dark">{label}</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
