const links = [
  { href: "/terms", label: "Terms and Conditions" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/data-security", label: "Data Security Policy" },
  { href: "/refund-policy", label: "Refund and Cancellation Policy" },
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
            Review LossQ's terms, privacy, security, refund, AI, and insurance disclaimers.
          </p>
        </div>

        <div className="mt-8 grid gap-4">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-3xl border border-white/10 bg-white/[0.035] p-6 font-semibold hover:border-cyan-300/40 hover:bg-white/[0.06]"
            >
              {link.label}
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}
