'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import {
  MarketingNav,
  Footer,
  SectionTitle,
} from '@/components/supportnova'
import {
  ArrowRight,
  Mail,
  Building,
  CheckCircle2,
  ShieldCheck,
  Headphones,
} from 'lucide-react'

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
  }

  return (
    <>
      <MarketingNav />

      <div className="ambient-mesh">
        <div className="ambient-blob-1" />
        <div className="ambient-blob-2" />
        <div className="tech-grid" />
      </div>

      <main className="section relative z-10 py-24">
        <div className="container max-w-4xl">
          <SectionTitle
            eyebrow="Direct Enterprise Engagement"
            title="Talk to the SupportNova Engineering Team"
            text="Whether you are preparing for high-volume peak periods, exploring dual-pipeline grounding, or reviewing competition compliance, we are here."
          />

          <div className="grid grid-cols-1 md:grid-cols-12 gap-8 mt-12">
            {/* Left Info Column */}
            <div className="md:col-span-5 flex flex-col justify-between">
              <div className="space-y-6">
                <div className="flex items-start gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-indigo-500/15 text-indigo-400 grid place-items-center shrink-0">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white m-0">Architecture Consultation</h4>
                    <p className="text-xs text-slate-400 m-0 mt-1 leading-relaxed">
                      Discuss custom policy chunking, prompt version tracking, and deterministic Python rule matrix design.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-cyan-500/15 text-cyan-400 grid place-items-center shrink-0">
                    <Building size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white m-0">Dedicated Enterprise Pilots</h4>
                    <p className="text-xs text-slate-400 m-0 mt-1 leading-relaxed">
                      Custom tenant deployment with 10,000+ complaint benchmarks and full Step 59 cryptographic audit trails.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/15 text-emerald-400 grid place-items-center shrink-0">
                    <Headphones size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white m-0">24/7 Operations Support</h4>
                    <p className="text-xs text-slate-400 m-0 mt-1 leading-relaxed">
                      Sub-minute MTTR with instant circuit breaker fallback to offline deterministic Python rules.
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-slate-900/60 border border-white/10 rounded-xl p-4 text-xs font-mono text-slate-400 mt-8">
                <div>NovaTech Robotics Support HQ</div>
                <div className="text-slate-500 mt-1">support@supportnova.ai · ResponseX</div>
              </div>
            </div>

            {/* Right Form Column */}
            <div className="md:col-span-7 bg-slate-900/60 border border-white/10 rounded-2xl p-8 backdrop-blur-md">
              {submitted ? (
                <div className="py-12 text-center">
                  <div className="w-14 h-14 rounded-full bg-emerald-500/20 text-emerald-400 grid place-items-center mx-auto mb-4">
                    <CheckCircle2 size={28} />
                  </div>
                  <h3 className="text-xl font-bold text-white mb-2">Message Dispatched</h3>
                  <p className="text-xs text-slate-300 max-w-sm mx-auto mb-6">
                    Our Lead Systems Architect and CX Operations team have received your request and will follow up within 2 hours.
                  </p>
                  <button
                    onClick={() => setSubmitted(false)}
                    className="button button-secondary text-xs"
                  >
                    Send another inquiry
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-[11px] font-mono uppercase text-slate-400 tracking-wider mb-1">
                      Work Email
                    </label>
                    <input
                      type="email"
                      className="field"
                      placeholder="cx-lead@company.com"
                      required
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[11px] font-mono uppercase text-slate-400 tracking-wider mb-1">
                        Organization
                      </label>
                      <input
                        type="text"
                        className="field"
                        placeholder="Company / Team"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-mono uppercase text-slate-400 tracking-wider mb-1">
                        Monthly Volume
                      </label>
                      <select className="field" defaultValue="1k-10k">
                        <option value="<1k">&lt; 1,000 complaints / mo</option>
                        <option value="1k-10k">1,000 – 10,000 complaints / mo</option>
                        <option value="10k+">10,000+ complaints / mo</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-mono uppercase text-slate-400 tracking-wider mb-1">
                      Operational Objectives
                    </label>
                    <textarea
                      className="field"
                      rows={5}
                      placeholder="Tell us about your current support workflows, policy verification challenges, or evaluation requirements..."
                      required
                    />
                  </div>

                  <button type="submit" className="button button-primary full mt-2 group">
                    <span>Submit Inquiry</span>
                    <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </>
  )
}
