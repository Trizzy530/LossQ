"use client";

import { useState } from "react";

export default function LandingPage() {
  const [email, setEmail] = useState("");
  const [joined, setJoined] = useState(false);

  return (
    <main className="min-h-screen bg-[#030508] text-white overflow-hidden">
      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.05)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(0,120,255,0.25),transparent_45%)]" />

      <nav className="relative z-10 flex justify-between items-center px-8 py-6 border-b border-blue-500/10 bg-black/40 backdrop-blur-xl">
        <h1 className="text-2xl font-black">Loss<span className="text-blue-500">Q</span></h1>

        <div className="flex gap-4">
          <a href="#features" className="hidden md:block text-slate-400 hover:text-white">Features</a>
          <a href="#pricing" className="hidden md:block text-slate-400 hover:text-white">Pricing</a>
          <a href="/login" className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold">
            Launch App
          </a>
        </div>
      </nav>

      <section className="relative z-10 min-h-[90vh] flex flex-col justify-center items-center text-center px-6">
        <p className="text-blue-400 text-xs tracking-[0.25em] uppercase border border-blue-500/20 bg-blue-500/10 rounded-full px-5 py-2 mb-8">
          AI Underwriting Intelligence
        </p>

        <h2 className="text-5xl md:text-8xl font-black leading-[0.95] max-w-5xl">
          Turn loss runs into
          <span className="block text-blue-500">underwriting intelligence.</span>
        </h2>

        <p className="text-slate-400 text-lg md:text-xl leading-8 max-w-2xl mt-8">
          LossQ helps brokers analyze claims, identify renewal concerns, generate AI memos,
          build carrier packets, and explain account risk faster.
        </p>

        <div className="flex flex-wrap gap-4 mt-10 justify-center">
          <a href="/login" className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-xl font-bold shadow-[0_0_45px_rgba(0,120,255,0.35)]">
            Launch Demo →
          </a>

          <a href="#features" className="border border-white/15 hover:border-blue-500 hover:bg-blue-500/10 px-8 py-4 rounded-xl font-bold">
            View Platform
          </a>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 mt-16 border border-blue-500/15 rounded-2xl overflow-hidden bg-[#0A1628] max-w-4xl w-full">
          <Stat value="AI" label="Claim Intelligence" />
          <Stat value="PDF" label="Carrier Packets" />
          <Stat value="LIVE" label="Policy Workspaces" />
        </div>
      </section>

      <section id="features" className="relative z-10 max-w-7xl mx-auto px-6 py-24">
        <p className="text-blue-400 text-xs tracking-[0.25em] uppercase mb-4">Platform Features</p>
        <h2 className="text-4xl md:text-6xl font-black max-w-3xl">
          Built for commercial renewal workflows.
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-1 mt-14 bg-blue-500/10 border border-blue-500/10 rounded-2xl overflow-hidden">
          <Feature title="Loss Run Uploads" text="Upload PDF, Excel, or CSV loss runs and organize claims by policy." />
          <Feature title="AI Claim Intelligence" text="Analyze severity, reserves, litigation risk, and renewal impact." />
          <Feature title="Policy Workspaces" text="Separate accounts, profiles, claims, Copilot answers, and exports." />
          <Feature title="Renewal Memo" text="Generate policy-specific underwriting memos and carrier narratives." />
          <Feature title="Carrier Packets" text="Export carrier-ready reports and submission materials." />
          <Feature title="AI Copilot" text="Ask underwriting questions against the selected account only." />
        </div>
      </section>

      <section id="pricing" className="relative z-10 max-w-7xl mx-auto px-6 py-24">
        <p className="text-blue-400 text-xs tracking-[0.25em] uppercase mb-4">Pricing</p>
        <h2 className="text-4xl md:text-6xl font-black">Simple SaaS pricing.</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-14">
          <Price tier="Starter" price="$99" />
          <Price tier="Pro" price="$249" featured />
          <Price tier="Agency" price="$499" />
        </div>
      </section>

      <section className="relative z-10 px-6 py-24 text-center">
        <div className="max-w-3xl mx-auto bg-[#0A1628] border border-blue-500/15 rounded-3xl p-10 md:p-16">
          <h2 className="text-4xl md:text-5xl font-black">Get early access</h2>
          <p className="text-slate-400 mt-5">Join the beta and start turning loss runs into underwriting intelligence.</p>

          {!joined ? (
            <div className="flex flex-col md:flex-row gap-3 max-w-xl mx-auto mt-8">
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@agency.com"
                className="flex-1 bg-white/5 border border-blue-500/20 rounded-lg px-5 py-4 outline-none"
              />
              <button
                onClick={() => setJoined(true)}
                className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-lg font-bold"
              >
                Join Beta
              </button>
            </div>
          ) : (
            <p className="text-blue-400 mt-8">✓ You’re on the list.</p>
          )}
        </div>
      </section>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="p-8 border-b md:border-b-0 md:border-r border-blue-500/15 last:border-0">
      <div className="text-4xl font-black text-blue-400">{value}</div>
      <div className="text-xs uppercase tracking-widest text-slate-500 mt-2">{label}</div>
    </div>
  );
}

function Feature({ title, text }: { title: string; text: string }) {
  return (
    <div className="bg-[#060D1A] hover:bg-[#0A1628] p-8">
      <h3 className="text-xl font-bold mb-3">{title}</h3>
      <p className="text-slate-400 leading-7">{text}</p>
    </div>
  );
}

function Price({ tier, price, featured = false }: { tier: string; price: string; featured?: boolean }) {
  return (
    <div className={`rounded-2xl p-8 bg-[#0A1628] border ${featured ? "border-blue-500 shadow-[0_0_45px_rgba(0,120,255,0.25)]" : "border-blue-500/15"}`}>
      <p className="text-blue-400 text-xs tracking-widest uppercase">{tier}</p>
      <h3 className="text-5xl font-black mt-4">{price}<span className="text-lg text-slate-500">/mo</span></h3>
      <a href="/login" className={`block mt-8 text-center rounded-lg py-4 font-bold ${featured ? "bg-blue-600" : "border border-white/15"}`}>
        Get Started
      </a>
    </div>
  );
}