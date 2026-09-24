'use client'

import React from 'react'
import Link from 'next/link'
import {
  MarketingNav,
  Footer,
  SectionTitle,
  ScrollReveal,
  TwoEngineArchitectureKey,
} from '@/components/supportnova'
import {
  Check,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react'

export default function PricingPage() {
  return (
    <>
      <MarketingNav />

      <div className="ambient-mesh">
        <div className="ambient-blob-1" />
        <div className="ambient-blob-2" />
        <div className="ambient-blob-3" />
        <div className="ambient-blob-4" />
        <div className="tech-grid" />
      </div>

      <main className="section relative z-10 py-20">
        <div className="container">
          <ScrollReveal variant="scale">
            <TwoEngineArchitectureKey />
          </ScrollReveal>

          <ScrollReveal variant="up" delay={50} className="mt-8">
            <SectionTitle
              eyebrow="Transparent Enterprise Pricing"
              title="Start Small. Scale With Ground-Truth Confidence."
              text="Predictable pricing for operations that demand source-grounded accountability and zero unauthorized AI promises."
            />
          </ScrollReveal>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
            {/* Starter (AI Engine Focused) */}
            <ScrollReveal variant="up" delay={100}>
              <div className="card-engine-ai p-8 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="pill-engine-ai text-[10px]">Engine 1: AI Reasoning</span>
                  </div>
                  <h3 className="text-2xl font-bold text-white mt-1 mb-2">Starter</h3>
                  <div className="flex items-baseline gap-1 my-4">
                    <span className="text-4xl font-extrabold text-white">$49</span>
                    <span className="text-xs text-slate-400">/ agent / month</span>
                  </div>
                  <p className="text-xs text-slate-300 mb-6">
                    Core complaint classification, sentiment analysis, and 8-department routing.
                  </p>

                  <ul className="space-y-3.5 text-xs text-slate-200">
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-indigo-400" />
                      <span>Up to 1,000 complaints / month</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-indigo-400" />
                      <span>AI Complaint Intelligence (NER)</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-indigo-400" />
                      <span>Standard 8-Department Routing</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-indigo-400" />
                      <span>Community &amp; Standard Support</span>
                    </li>
                  </ul>
                </div>

                <Link href="/dashboard" className="button button-secondary full mt-8">
                  Start Pilot Trial
                </Link>
              </div>
            </ScrollReveal>

            {/* Pro (Two-Engine Parity - Most Popular) */}
            <ScrollReveal variant="scale" delay={150}>
              <div className="card-dual-engine p-8 flex flex-col justify-between h-full relative shadow-[0_0_35px_rgba(99,102,241,0.35)] border-2 border-indigo-400/60">
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 text-white text-[10.5px] font-mono font-bold uppercase tracking-wider px-3.5 py-1 rounded-full shadow-lg">
                  Dual-Engine Parity
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="pill-status-verified text-[10px]">Both Engines Gated</span>
                  </div>
                  <h3 className="text-2xl font-bold text-white mt-1 mb-2">Pro Ground-Truth</h3>
                  <div className="flex items-baseline gap-1 my-4">
                    <span className="text-4xl font-extrabold text-white">$99</span>
                    <span className="text-xs text-slate-400">/ agent / month</span>
                  </div>
                  <p className="text-xs text-slate-300 mb-6">
                    Full dual-pipeline validation, 100-rule matrix, and Step 57 review queue.
                  </p>

                  <ul className="space-y-3.5 text-xs text-slate-200">
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Up to 10,000 complaints / month</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span><b>Deterministic Python Verifier</b></span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Policy Precedence Hierarchy Resolver</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-emerald-400" />
                      <span>Step 57 Manual Review Queue</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Real-Time SLA Risk Countdown Clocks</span>
                    </li>
                  </ul>
                </div>

                <Link href="/dashboard" className="button button-primary full mt-8 group">
                  <span>Deploy Pro Workspace</span>
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                </Link>
              </div>
            </ScrollReveal>

            {/* Enterprise (Python Truth & Custom Rules) */}
            <ScrollReveal variant="up" delay={200}>
              <div className="card-engine-python p-8 flex flex-col justify-between h-full">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="pill-engine-python text-[10px]">Deterministic Security</span>
                  </div>
                  <h3 className="text-2xl font-bold text-white mt-1 mb-2">Enterprise</h3>
                  <div className="flex items-baseline gap-1 my-4">
                    <span className="text-4xl font-extrabold text-white">Custom</span>
                    <span className="text-xs text-slate-400">/ tailored SLA</span>
                  </div>
                  <p className="text-xs text-slate-300 mb-6">
                    Dedicated tenant, custom policy parsers, Step 59 immutable cryptographic ledger.
                  </p>

                  <ul className="space-y-3.5 text-xs text-slate-200">
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Unlimited complaint volume</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Custom 100+ rule matrix integrations</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-emerald-400" />
                      <span>Step 59 Immutable Audit Ledger Export</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>99.99% Uptime SLA with 24/7 Engineers</span>
                    </li>
                    <li className="flex items-center gap-2.5">
                      <Check size={15} className="text-cyan-400" />
                      <span>Dedicated Technical Account Manager</span>
                    </li>
                  </ul>
                </div>

                <Link href="/contact" className="button button-secondary full mt-8">
                  Contact Enterprise Team
                </Link>
              </div>
            </ScrollReveal>
          </div>
        </div>
      </main>

      <Footer />
    </>
  )
}
