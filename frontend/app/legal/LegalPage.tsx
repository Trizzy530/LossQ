type LegalSection = {
  heading: string;
  body: string[];
};

export default function LegalPage({
  title,
  subtitle,
  sections,
}: {
  title: string;
  subtitle: string;
  sections: LegalSection[];
}) {
  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <section className="mx-auto max-w-4xl px-6 py-14">
        <a href="/" className="text-sm text-cyan-300 hover:text-cyan-200">
          ← Back to LossQ
        </a>

        <div className="mt-8 rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl">
          <p className="text-sm font-semibold text-cyan-300">LossQ Legal</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight">{title}</h1>
          <p className="mt-4 text-slate-300">{subtitle}</p>
          <p className="mt-4 text-xs text-slate-500">Effective Date: June 10, 2026</p>
        </div>

        <div className="mt-8 space-y-5">
          {sections.map((section) => (
            <article
              key={section.heading}
              className="rounded-3xl border border-white/10 bg-white/[0.035] p-6"
            >
              <h2 className="text-xl font-bold text-white">{section.heading}</h2>
              <div className="mt-4 space-y-3 text-sm leading-7 text-slate-300">
                {section.body.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
            </article>
          ))}
        </div>

        <div className="mt-8 rounded-3xl border border-amber-400/20 bg-amber-400/10 p-5 text-sm text-amber-100">
          These materials are starter legal templates for LossQ and should be reviewed by legal counsel before public launch.
        </div>
      </section>
    </main>
  );
}
