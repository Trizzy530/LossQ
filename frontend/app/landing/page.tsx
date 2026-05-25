"use client";

import { useEffect, useState } from "react";

export default function LandingPage() {
  const [email, setEmail] = useState("");
  const [joined, setJoined] = useState(false);

  useEffect(() => {
    const cursor = document.getElementById("cursor");
    const ring = document.getElementById("cursorRing");

    if (!cursor || !ring) return;

    let mx = 0;
    let my = 0;
    let rx = 0;
    let ry = 0;

    const move = (e: MouseEvent) => {
      mx = e.clientX;
      my = e.clientY;
      cursor.style.left = `${mx}px`;
      cursor.style.top = `${my}px`;
    };

    const animate = () => {
      rx += (mx - rx) * 0.12;
      ry += (my - ry) * 0.12;
      ring.style.left = `${rx}px`;
      ring.style.top = `${ry}px`;
      requestAnimationFrame(animate);
    };

    document.addEventListener("mousemove", move);
    animate();

    return () => document.removeEventListener("mousemove", move);
  }, []);

  function handleSignup() {
    if (!email || !email.includes("@")) {
      alert("Enter a valid email.");
      return;
    }

    setJoined(true);
  }

  return (
    <main className="min-h-screen bg-[#030508] text-[#F0F4FF] overflow-x-hidden">
      <div id="cursor" className="hidden md:block fixed w-3 h-3 bg-blue-500 rounded-full pointer-events-none z-[9999] -translate-x-1/2 -translate-y-1/2 mix-blend-screen" />
      <div id="cursorRing" className="hidden md:block fixed w-9 h-9 border border-blue-400/50 rounded-full pointer-events-none z-[9998] -translate-x-1/2 -translate-y-1/2" />

      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.04)_1px,transparent_1px)] bg-[size:60px_60px] pointer-events-none" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_center,rgba(0,120,255,0.12),transparent_55%)] pointer-events-none" />

      <nav className="fixed top-0 left-0 right-0 z-50 px-8 md:px-12 py-5 flex items-center justify-between bg-black/70 backdrop-blur-xl border-b border-blue-500/10">
        <a href="/landing" className="text-2xl font-black tracking-tight">
          Loss<span className="text-blue-500">Q</span>
        </a>

        <div className="hidden md:flex items-center gap-8 text-xs uppercase tracking-[0.2em] text-slate-400">
          <a href="#features" className="hover:text-white">Features</a>
          <a href="#how" className="hover:text-white">How It Works</a>
          <a href="#pricing" className="hover:text-white">Pricing</a>
          <a href="/login" className="border border-blue-500 text-blue-400 px-5 py-2 rounded hover:bg-blue-600 hover:text-white">
            Launch App
          </a>
        </div>
      </nav>

      <section className="relative z-10 min-h-screen flex flex-col items-center justify-center text-center px-6 pt-32">
        <div className="text-blue-400 text-xs tracking-[0.25em] uppercase border border-blue-500/20 bg-blue-500/5 px-5 py-2 rounded-full mb-10">
          AI Underwriting Intelligence
        </div>

        <h1 className="text-5xl md:text-8xl font-black leading-[0.95] tracking-tight max-w-5xl">
          Insurance Loss Runs.
          <span className="block text-blue-500">Instant.</span>
          <span className="block text-transparent [-webkit-text-stroke:1px_#0078ff]">
            Intelligent.
          </span>
        </h1>

        <p className="text-slate-400 text-lg md:text-xl leading-8 max-w-2xl mt-8">
          LossQ helps brokers process loss runs, analyze claim severity, generate renewal memos,
          create carrier packets, and explain account risk faster.
        </p>

        <div className="flex flex-wrap gap-4 justify-center mt-10">
          <a href="/login" className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-lg font-bold shadow-[0_0_40px_rgba(0,120,255,0.35)]">
            Launch Demo →
          </a>

          <a href="#how" className="border border-white/15 hover:border-blue-500 hover:bg-blue-500/10 px-8 py-4 rounded-lg font-bold">
            See How It Works
          </a>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 mt-16 border border-blue-500/15 rounded-2xl overflow-hidden bg-[#0A1628] max-w-3xl w-full">
          <Stat value="<5s" label="Loss Run Processing" />
          <Stat value="AI" label="Claim Intelligence" />
          <Stat value="PDF" label="Carrier Reports" />
        </div>
      </section>

      <Ticker />

      <section id="features" className="relative z-10 max-w-7xl mx-auto px-6 py-28">
        <p className="text-blue-400 text-xs tracking-[0.25em] uppercase mb-5">Platform Features</p>

        <h2 className="text-4xl md:text-6xl font-black max-w-3xl leading-tight">
          Everything an underwriter <span className="text-blue-500">actually</span> needs.
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-px mt-16 bg-blue-500/15 border border-blue-500/15 rounded-2xl overflow-hidden">
          <Feature icon="⚡" title="Instant Loss Run Processing" text="Upload PDF, Excel, or CSV loss runs and organize claims by policy workspace." tag="// File → Intelligence" />
          <Feature icon="🧠" title="Claims Intelligence Panel" text="Clickable claim analysis with severity, reserve adequacy, litigation risk, and renewal impact." tag="// AI Claim Analysis" />
          <Feature icon="📊" title="Renewal Risk Scoring" text="Policy-specific summaries, trend analytics, reserve pressure, and underwriting risk indicators." tag="// Risk Engine" />
          <Feature icon="📋" title="Carrier Packet Generation" text="Generate carrier-ready PDFs, executive reports, and submission materials in one click." tag="// Submission Ready" />
          <Feature icon="✍️" title="Broker Narrative Generator" text="Create professional renewal memos and carrier narratives based on the selected policy." tag="// Memo Builder" />
          <Feature icon="🏢" title="Multi-Policy Workspaces" text="Separate business profiles, policy numbers, claims, charts, Copilot answers, and exports." tag="// Account Isolation" />
        </div>
      </section>

      <section id="how" className="relative z-10 px-6 py-28 bg-gradient-to-b from-transparent via-[#060D1A] to-transparent">
        <div className="max-w-7xl mx-auto">
          <p className="text-blue-400 text-xs tracking-[0.25em] uppercase mb-5">How It Works</p>

          <h2 className="text-4xl md:text-6xl font-black max-w-3xl leading-tight">
            From upload to insight in <span className="text-blue-500">seconds.</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mt-16">
            <Step num="01" title="Upload Loss Run" text="Drop in PDF, Excel, or CSV claim data." />
            <Step num="02" title="AI Parses Claims" text="LossQ extracts, normalizes, and organizes the claim information." />
            <Step num="03" title="Analyze Risk" text="See severity, litigation exposure, reserves, trends, and renewal risk." />
            <Step num="04" title="Export & Submit" text="Generate renewal memos, loss runs, and carrier-ready packets." />
          </div>
        </div>
      </section>

      <section id="pricing" className="relative z-10 max-w-7xl mx-auto px-6 py-28">
        <p className="text-blue-400 text-xs tracking-[0.25em] uppercase mb-5">Pricing</p>

        <h2 className="text-4xl md:text-6xl font-black max-w-3xl leading-tight">
          Simple pricing. <span className="text-blue-500">No surprises.</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-16">
          <Price tier="Starter" price="$99" desc="For solo brokers testing AI loss run workflows." features={["1 user", "20 uploads/month", "AI claim intelligence", "PDF exports", "Email support"]} />
          <Price featured tier="Pro" price="$249" desc="For agencies running active renewals and submissions." features={["Up to 5 users", "Unlimited uploads", "Renewal memos", "Carrier packets", "Priority support"]} />
          <Price tier="Agency" price="$499" desc="For larger teams needing full platform access." features={["Unlimited users", "Unlimited uploads", "All Pro features", "Team workflows", "Dedicated support"]} />
        </div>
      </section>

      <section id="waitlist" className="relative z-10 px-6 py-28 text-center">
        <div className="max-w-3xl mx-auto bg-[#0A1628] border border-blue-500/15 rounded-3xl p-10 md:p-20 relative overflow-hidden">
          <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl" />

          <div className="relative">
            <h2 className="text-4xl md:text-6xl font-black leading-tight">
              Get Early Access to LossQ
            </h2>

            <p className="text-slate-400 text-lg leading-8 mt-6">
              Join the beta and start turning messy loss runs into underwriting intelligence.
            </p>

            {!joined ? (
              <div className="flex flex-col md:flex-row gap-3 max-w-xl mx-auto mt-10">
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@agency.com"
                  className="flex-1 bg-white/5 border border-blue-500/20 rounded-lg px-5 py-4 outline-none focus:border-blue-500"
                />

                <button
                  onClick={handleSignup}
                  className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-lg font-bold"
                >
                  Join Beta
                </button>
              </div>
            ) : (
              <p className="text-blue-400 font-mono mt-10">
                ✓ You’re on the list. We’ll be in touch shortly.
              </p>
            )}

            <p className="text-slate-500 text-xs tracking-widest uppercase mt-5">
              No credit card required · Founder pricing available
            </p>
          </div>
        </div>
      </section>

      <footer className="relative z-10 border-t border-blue-500/15 px-8 py-10 flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="font-black text-xl">Loss<span className="text-blue-500">Q</span></div>

        <div className="flex gap-6 text-xs tracking-widest uppercase text-slate-500">
          <a href="#features" className="hover:text-white">Features</a>
          <a href="#pricing" className="hover:text-white">Pricing</a>
          <a href="mailto:hello@lossq.com" className="hover:text-white">Contact</a>
        </div>

        <p className="text-xs text-slate-500">© 2026 LossQ. All rights reserved.</p>
      </footer>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="p-7 border-b md:border-b-0 md:border-r border-blue-500/15 last:border-0">
      <div className="text-4xl font-black text-blue-400">{value}</div>
      <div className="text-xs tracking-widest uppercase text-slate-500 mt-2">{label}</div>
    </div>
  );
}

function Feature({ icon, title, text, tag }: { icon: string; title: string; text: string; tag: string }) {
  return (
    <div className="bg-[#060D1A] hover:bg-[#0A1628] p-9 transition">
      <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/15 flex items-center justify-center mb-6 text-xl">
        {icon}
      </div>

      <h3 className="text-xl font-bold mb-3">{title}</h3>
      <p className="text-slate-400 leading-7 text-sm">{text}</p>
      <p className="text-blue-400 font-mono text-xs tracking-widest mt-6">{tag}</p>
    </div>
  );
}

function Step({ num, title, text }: { num: string; title: string; text: string }) {
  return (
    <div className="text-center">
      <div className="w-16 h-16 mx-auto rounded-full border border-blue-500 bg-[#0A1628] text-blue-400 flex items-center justify-center font-mono shadow-[0_0_30px_rgba(0,120,255,0.25)]">
        {num}
      </div>

      <h4 className="font-bold text-lg mt-6 mb-3">{title}</h4>
      <p className="text-slate-400 text-sm leading-6">{text}</p>
    </div>
  );
}

function Price({
  tier,
  price,
  desc,
  features,
  featured = false,
}: {
  tier: string;
  price: string;
  desc: string;
  features: string[];
  featured?: boolean;
}) {
  return (
    <div className={`relative bg-[#0A1628] border rounded-2xl p-9 ${featured ? "border-blue-500 shadow-[0_0_45px_rgba(0,120,255,0.25)]" : "border-blue-500/15"}`}>
      {featured && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-mono tracking-widest px-4 py-1 rounded-full">
          MOST POPULAR
        </div>
      )}

      <p className="text-blue-400 font-mono text-xs tracking-widest uppercase">{tier}</p>
      <h3 className="text-5xl font-black mt-5">{price}<span className="text-lg text-slate-500">/mo</span></h3>
      <p className="text-slate-400 text-sm leading-6 mt-4 mb-8">{desc}</p>

      <ul className="space-y-3 mb-9">
        {features.map((feature) => (
          <li key={feature} className="text-slate-400 text-sm border-b border-white/5 pb-3">
            <span className="text-blue-400 mr-2">→</span>{feature}
          </li>
        ))}
      </ul>

      <a href="/login" className={`block text-center rounded-lg py-4 font-bold ${featured ? "bg-blue-600 hover:bg-blue-700" : "border border-white/15 hover:border-blue-500 hover:bg-blue-500/10"}`}>
        Get Started
      </a>
    </div>
  );
}

function Ticker() {
  const items = [
    "Instant Loss Run Processing",
    "AI Renewal Risk Scoring",
    "Carrier Packet Generation",
    "Claims Intelligence Panel",
    "Executive PDF Reports",
    "Broker Narrative Generator",
    "Multi-Policy Workspaces",
    "Timeline Analytics",
  ];

  return (
    <div className="relative z-10 overflow-hidden border-y border-blue-500/15 bg-[#060D1A] py-4">
      <div className="flex gap-16 whitespace-nowrap animate-[ticker_24s_linear_infinite]">
        {[...items, ...items].map((item, index) => (
          <span key={`${item}-${index}`} className="text-slate-500 text-xs tracking-[0.25em] uppercase shrink-0">
            <span className="text-blue-400 mr-2">→</span>{item}
          </span>
        ))}
      </div>

      <style jsx>{`
        @keyframes ticker {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
