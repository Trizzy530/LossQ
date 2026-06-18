const links = [
  { href: "/terms", label: "Terms of Service" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/data-security", label: "Data Security Policy" },
  { href: "/refund-policy", label: "Refund and Cancellation Policy" },
  { href: "/cancellation-policy", label: "Cancellation Policy" },
  { href: "/ai-disclaimer", label: "AI Disclaimer" },
  { href: "/insurance-disclaimer", label: "Insurance Disclaimer" },
];

export default function LegalIndexPage() {
  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <section className="mx-auto max-w-4xl px-6 py-14">
        <a href="/" className="text-sm text-cyan-300 hover:text-cyan-200">
          ← Back to LossQ
        </a>

        <div className="mt-8 rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl">
          <p className="text-sm font-semibold text-cyan-300">LossQ Legal Center</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight">Legal Policies</h1>
          <p className="mt-4 text-slate-300">
            Review LossQ's terms, privacy, security, billing, cancellation, AI, and insurance disclaimers.
          </p>

          <div className="mt-8 grid gap-3">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="rounded-2xl border border-white/10 bg-slate-950/50 px-5 py-4 text-slate-100 hover:border-cyan-300/40 hover:bg-cyan-400/10"
              >
                {link.label}
              </a>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
